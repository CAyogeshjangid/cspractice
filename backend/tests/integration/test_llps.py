"""M13 — LLP module: masters, partners, Form 11/8 working papers."""
from __future__ import annotations

from tests.conftest import post, register_firm

LLP = {"llpin": "AAB-1234", "name": "Fixture Advisors LLP",
       "registered_address": "9 Partner Row, Delhi", "total_contribution": 1000000}


async def test_llp_crud_and_llpin_uniqueness(firm) -> None:
    created = (await post(firm.executive, "/llps", LLP)).json()
    assert created["llpin"] == "AAB-1234"

    dup = await post(firm.manager, "/llps", {**LLP, "name": "Other LLP"})
    assert dup.status_code == 409

    listing = await firm.viewer.get("/api/v1/llps")
    assert listing.headers["X-Total-Count"] == "1"

    res = await post(firm.executive, f"/llps/{created['id']}",
                     {**LLP, "email": "llp@example.com"}, method="PUT")
    assert res.json()["email"] == "llp@example.com"

    # soft delete: Partner only; llpin becomes reusable afterwards
    res = await post(firm.executive, f"/llps/{created['id']}",
                     {"reason": "denied"}, method="DELETE")
    assert res.status_code == 403
    res = await post(firm.partner, f"/llps/{created['id']}",
                     {"reason": "client exited"}, method="DELETE")
    assert res.status_code == 204
    assert (await firm.viewer.get("/api/v1/llps")).headers["X-Total-Count"] == "0"
    assert (await post(firm.executive, "/llps", LLP)).status_code == 201


async def test_partners_and_designated_counts(firm) -> None:
    llp_id = (await post(firm.executive, "/llps", LLP)).json()["id"]
    await post(firm.executive, f"/llps/{llp_id}/partners", {
        "name": "P. Designated", "dpin": "01234567", "is_designated": True,
        "contribution": 600000, "profit_share_percent": 60,
    })
    await post(firm.executive, f"/llps/{llp_id}/partners", {
        "name": "Q. Ordinary", "contribution": 400000, "profit_share_percent": 40,
    })
    await post(firm.executive, f"/llps/{llp_id}/partners", {
        "name": "R. Ceased", "is_designated": True, "cessation_date": "2024-03-31",
    })

    partners = (await firm.viewer.get(f"/api/v1/llps/{llp_id}/partners")).json()
    assert len(partners) == 3

    # working-paper GET derives ACTIVE partner counts from the master
    paper = (await firm.viewer.get(
        f"/api/v1/llps/{llp_id}/working-papers/2026/form11")).json()
    assert paper["partner_count"] == 2
    assert paper["designated_partner_count"] == 1


async def test_working_paper_lifecycle_draft_finalize_readonly(firm) -> None:
    llp_id = (await post(firm.executive, "/llps", LLP)).json()["id"]

    # draft saves; typed schema rejects junk
    res = await post(firm.executive, f"/llps/{llp_id}/working-papers/2026/form11",
                     {"payload": {"surprise": "x"}}, method="PUT")
    assert res.status_code == 422
    problems = res.json()["detail"]["problems"]
    assert any("total_contribution_received" in p for p in problems)
    assert any("unknown field: surprise" in p for p in problems)

    res = await post(firm.executive, f"/llps/{llp_id}/working-papers/2026/form11",
                     {"payload": {"total_contribution_received": "1000000"}}, method="PUT")
    assert res.status_code == 200
    assert res.json()["status"] == "draft"

    # finalising requires the SRN
    res = await post(firm.manager, f"/llps/{llp_id}/working-papers/2026/form11",
                     {"payload": {"total_contribution_received": "1000000"},
                      "status": "finalized"}, method="PUT")
    assert res.status_code == 422
    res = await post(firm.manager, f"/llps/{llp_id}/working-papers/2026/form11",
                     {"payload": {"total_contribution_received": "1000000"},
                      "status": "finalized", "srn": "F1122"}, method="PUT")
    assert res.status_code == 200

    # finalised papers are read-only
    res = await post(firm.manager, f"/llps/{llp_id}/working-papers/2026/form11",
                     {"payload": {"total_contribution_received": "2"}}, method="PUT")
    assert res.status_code == 409

    # Form 8 is independent per (fy, form)
    res = await post(firm.executive, f"/llps/{llp_id}/working-papers/2026/form8",
                     {"payload": {"turnover": "5000000", "assets_total": "2000000",
                                  "liabilities_total": "1000000"}}, method="PUT")
    assert res.status_code == 200


async def test_llp_rbac_and_tenancy(firm, make_client) -> None:
    res = await post(firm.viewer, "/llps", LLP)
    assert res.status_code == 403

    llp_id = (await post(firm.executive, "/llps", LLP)).json()["id"]
    rival = make_client()
    await register_firm(rival, "rival-llp@example.com", "Rival")
    assert (await rival.get(f"/api/v1/llps/{llp_id}")).status_code == 404
    assert (await rival.get("/api/v1/llps")).json() == []
    # rival can reuse the LLPIN — uniqueness is per firm
    assert (await post(rival, "/llps", LLP)).status_code == 201
