"""Directors, disclosures, shareholders, taxonomies, company edit (M3)."""
from __future__ import annotations

from tests.conftest import post, register_firm

COMPANY = {"cin": "U74999MH2020PTC123456", "name": "Fixture Pvt Ltd"}


async def _company(client) -> str:
    res = await post(client, "/companies", COMPANY)
    return res.json()["id"]


async def test_director_crud_and_fy_filter(firm) -> None:
    cid = await _company(firm.manager)
    res = await post(firm.manager, f"/companies/{cid}/directors", {
        "name": "A. Director", "din": "01234567",
        "appointment_date": "2020-06-01", "cessation_date": "2025-03-01",
    })
    assert res.status_code == 201
    did = res.json()["id"]
    await post(firm.manager, f"/companies/{cid}/directors", {
        "name": "B. Newer", "din": "07654321", "appointment_date": "2025-06-01",
    })

    # FY 2024-25 (ends 2025): A was in office; B not yet appointed
    fy2025 = (await firm.viewer.get(f"/api/v1/companies/{cid}/directors?fy=2025")).json()
    assert [d["name"] for d in fy2025] == ["A. Director"]
    # FY 2025-26: A ceased before it started; B in office
    fy2026 = (await firm.viewer.get(f"/api/v1/companies/{cid}/directors?fy=2026")).json()
    assert [d["name"] for d in fy2026] == ["B. Newer"]

    # update with audit diff
    res = await post(firm.executive, f"/companies/{cid}/directors/{did}", {
        "name": "A. Director", "din": "01234567", "designation": "Managing Director",
        "appointment_date": "2020-06-01", "cessation_date": "2025-03-01",
    }, method="PUT")
    assert res.status_code == 200
    assert res.json()["designation"] == "Managing Director"


async def test_disclosure_upsert_per_fy(firm) -> None:
    cid = await _company(firm.executive)
    did = (await post(firm.executive, f"/companies/{cid}/directors",
                      {"name": "D. Disclosure"})).json()["id"]

    res = await post(firm.executive, f"/companies/{cid}/directors/{did}/disclosures/2026",
                     {"mbp1_received": "2025-04-10"}, method="PUT")
    assert res.status_code == 200
    assert res.json()["mbp1_received"] == "2025-04-10"

    # second PUT for the same FY updates, not duplicates
    await post(firm.executive, f"/companies/{cid}/directors/{did}/disclosures/2026",
               {"mbp1_received": "2025-04-10", "dir8_received": "2025-04-12"}, method="PUT")
    listing = (await firm.viewer.get(
        f"/api/v1/companies/{cid}/directors/{did}/disclosures")).json()
    assert len(listing) == 1
    assert listing[0]["dir8_received"] == "2025-04-12"


async def test_viewer_cannot_mutate_masters(firm) -> None:
    cid = await _company(firm.partner)
    assert (await post(firm.viewer, f"/companies/{cid}/directors",
                       {"name": "Nope"})).status_code == 403
    assert (await post(firm.viewer, f"/companies/{cid}/shareholders",
                       {"name": "Nope"})).status_code == 403
    assert (await post(firm.viewer, "/taxonomies/industries",
                       {"name": "Nope"})).status_code == 403


async def test_shareholders_totals_and_warning(firm) -> None:
    cid = await _company(firm.manager)
    await post(firm.manager, f"/companies/{cid}/shareholders",
               {"name": "Holder A", "shares": 60, "percentage": 60})
    await post(firm.manager, f"/companies/{cid}/shareholders",
               {"name": "Holder B", "shares": 30, "percentage": 30})

    from decimal import Decimal

    res = (await firm.viewer.get(f"/api/v1/companies/{cid}/shareholders")).json()
    assert Decimal(res["total_percentage"]) == 90
    assert res["percentage_warning"] is True  # 90 ≠ 100 beyond tolerance

    sid = res["shareholders"][1]["id"]
    await post(firm.manager, f"/companies/{cid}/shareholders/{sid}",
               {"name": "Holder B", "shares": 40, "percentage": 40}, method="PUT")
    res = (await firm.viewer.get(f"/api/v1/companies/{cid}/shareholders")).json()
    assert res["percentage_warning"] is False


async def test_taxonomies_firm_scoped_unique(firm, make_client) -> None:
    res = await post(firm.executive, "/taxonomies/professional-groups", {"name": "Listed clients"})
    assert res.status_code == 201
    dup = await post(firm.partner, "/taxonomies/professional-groups", {"name": "Listed clients"})
    assert dup.status_code == 409

    # a different firm can reuse the same name
    other = make_client()
    await register_firm(other, "other-firm@example.com", "Other Firm")
    res = await post(other, "/taxonomies/professional-groups", {"name": "Listed clients"})
    assert res.status_code == 201


async def test_company_partial_update_with_audit_diff(firm) -> None:
    cid = await _company(firm.partner)
    res = await post(firm.executive, f"/companies/{cid}",
                     {"agm_date": "2026-09-30"}, method="PUT")
    assert res.status_code == 200
    assert res.json()["agm_date"] == "2026-09-30"
    assert res.json()["name"] == COMPANY["name"]  # untouched fields survive

    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ActivityLog

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        entry = (
            await session.execute(
                select(ActivityLog).where(
                    ActivityLog.entity_type == "company", ActivityLog.action == "update"
                )
            )
        ).scalars().one()
    assert entry.diff["after"] == {"agm_date": "2026-09-30"}


async def test_cross_tenant_masters_are_404(firm, make_client) -> None:
    cid = await _company(firm.partner)
    rival = make_client()
    await register_firm(rival, "rival-masters@example.com", "Rival")
    assert (await post(rival, f"/companies/{cid}/directors",
                       {"name": "Intruder"})).status_code == 404
    assert (await rival.get(f"/api/v1/companies/{cid}/shareholders")).status_code == 404