"""M11 — auditors (+appointments), PCS master, DSC tracker."""
from __future__ import annotations

from tests.conftest import post, register_firm

COMPANY = {"cin": "U74999MH2020PTC787878", "name": "Practice Fixture Pvt Ltd"}


async def test_auditor_master_and_appointments(firm) -> None:
    res = await post(firm.executive, "/auditors", {
        "firm_name": "S. Auditors & Co.", "frn": "123456W", "email": "audit@example.com",
    })
    assert res.status_code == 201
    auditor_id = res.json()["id"]

    # duplicate FRN within the firm → 409
    dup = await post(firm.manager, "/auditors", {"firm_name": "Other", "frn": "123456W"})
    assert dup.status_code == 409

    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    res = await post(firm.executive, f"/companies/{cid}/auditor-appointments", {
        "auditor_id": auditor_id, "appointed_from_fy": 2025, "adt1_srn": "T9988",
    })
    assert res.status_code == 201

    listing = (await firm.viewer.get(f"/api/v1/companies/{cid}/auditor-appointments")).json()
    assert len(listing) == 1
    assert listing[0]["auditor_name"] == "S. Auditors & Co."
    assert listing[0]["current"] is True  # open-ended = current auditor
    assert listing[0]["adt1_srn"] == "T9988"


async def test_pcs_master(firm) -> None:
    res = await post(firm.manager, "/pcs", {
        "name": "R. Sharma", "membership_no": "F1234", "cop_no": "C567",
        "firm_name": "Sharma & Associates",
    })
    assert res.status_code == 201
    dup = await post(firm.manager, "/pcs", {"name": "Other", "membership_no": "F1234"})
    assert dup.status_code == 409
    listing = (await firm.viewer.get("/api/v1/pcs")).json()
    assert [p["membership_no"] for p in listing] == ["F1234"]


async def test_dsc_tracker_crud_sorted_by_expiry(firm) -> None:
    await post(firm.executive, "/dsc-tokens", {
        "holder_name": "Late Expiry", "expiry_date": "2027-12-31", "token_color": "blue",
    })
    res = await post(firm.executive, "/dsc-tokens", {
        "holder_name": "Soon Expiry", "expiry_date": "2026-08-01", "token_number": "TK-9",
    })
    token_id = res.json()["id"]

    listing = (await firm.viewer.get("/api/v1/dsc-tokens")).json()
    assert [t["holder_name"] for t in listing] == ["Soon Expiry", "Late Expiry"]

    res = await post(firm.manager, f"/dsc-tokens/{token_id}", {
        "holder_name": "Soon Expiry", "expiry_date": "2028-01-01",
    }, method="PUT")
    assert res.status_code == 200
    listing = (await firm.viewer.get("/api/v1/dsc-tokens")).json()
    assert listing[-1]["holder_name"] == "Soon Expiry"  # re-sorted after renewal


async def test_practice_masters_rbac_and_tenancy(firm, make_client) -> None:
    for path, body in (
        ("/auditors", {"firm_name": "X & Co", "frn": "999999X"}),
        ("/pcs", {"name": "X", "membership_no": "F9"}),
        ("/dsc-tokens", {"holder_name": "X"}),
    ):
        res = await post(firm.viewer, path, body)
        assert res.status_code == 403, path

    await post(firm.executive, "/auditors", {"firm_name": "Mine & Co", "frn": "111111M"})
    rival = make_client()
    await register_firm(rival, "rival-practice@example.com", "Rival")
    assert (await rival.get("/api/v1/auditors")).json() == []
    assert (await rival.get("/api/v1/dsc-tokens")).json() == []
    # rival can reuse the FRN — uniqueness is per firm
    res = await post(rival, "/auditors", {"firm_name": "Rival View", "frn": "111111M"})
    assert res.status_code == 201
