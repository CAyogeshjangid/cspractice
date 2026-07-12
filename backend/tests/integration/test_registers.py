"""M9 — statutory registers on the append-only architecture (PRD §8).

Acceptance: edits create versions with priors queryable; no hard delete
anywhere; deletes carry reason/actor and stay in history; exports carry an
as-on stamp; typed schemas reject junk; the DB grant forbids UPDATE."""
from __future__ import annotations

from tests.conftest import post, register_firm

COMPANY = {"cin": "U74999MH2020PTC343434", "name": "Registers Fixture Pvt Ltd"}

MEMBER = {
    "folio_no": "F-001",
    "name": "Asha Holder",
    "shares_held": "5000",
    "date_of_entry": "2020-04-01",
}


async def _company(firm) -> str:
    return (await post(firm.manager, "/companies", COMPANY)).json()["id"]


async def test_summary_lists_all_14_registers_with_schemas(firm) -> None:
    cid = await _company(firm)
    res = await firm.viewer.get(f"/api/v1/companies/{cid}/registers")
    assert res.status_code == 200
    summary = res.json()
    assert len(summary) == 14
    members = next(r for r in summary if r["type"] == "members")
    assert members["section"].startswith("S.88")
    assert members["mandatory"] is True
    assert "folio_no" in members["required_fields"]
    assert all(r["entries"] == 0 for r in summary)


async def test_append_only_lifecycle_create_amend_history(firm) -> None:
    cid = await _company(firm)
    created = (
        await post(firm.executive, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    ).json()
    key = created["entry_key"]
    assert created["version"] == 1

    # amend: shares change → version 2; version 1 remains queryable
    amended = (
        await post(firm.executive, f"/register-entries/{key}",
                   {"payload": {**MEMBER, "shares_held": "7500"},
                    "expected_version": 1}, method="PUT")
    ).json()
    assert amended["version"] == 2

    history = (await firm.viewer.get(f"/api/v1/register-entries/{key}/history")).json()
    assert [h["version"] for h in history] == [1, 2]
    assert history[0]["payload"]["shares_held"] == "5000"  # prior version intact
    assert history[1]["payload"]["shares_held"] == "7500"

    current = (await firm.viewer.get(f"/api/v1/companies/{cid}/registers/members")).json()
    assert len(current) == 1
    assert current[0]["version"] == 2


async def test_stale_amend_gets_409_not_lost_update(firm) -> None:
    cid = await _company(firm)
    key = (
        await post(firm.executive, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    ).json()["entry_key"]
    await post(firm.manager, f"/register-entries/{key}",
               {"payload": {**MEMBER, "shares_held": "6000"}, "expected_version": 1},
               method="PUT")
    # a second editor still holding v1 must not silently clobber v2
    res = await post(firm.executive, f"/register-entries/{key}",
                     {"payload": {**MEMBER, "shares_held": "9999"}, "expected_version": 1},
                     method="PUT")
    assert res.status_code == 409


async def test_delete_is_versioned_partner_only_and_stays_in_history(firm) -> None:
    cid = await _company(firm)
    key = (
        await post(firm.executive, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    ).json()["entry_key"]

    # PRD §9/§8: register deletion is a Partner action with a mandatory reason
    res = await post(firm.executive, f"/register-entries/{key}",
                     {"reason": "entered in error"}, method="DELETE")
    assert res.status_code == 403
    res = await post(firm.partner, f"/register-entries/{key}",
                     {"reason": "entered in error"}, method="DELETE")
    assert res.status_code == 200

    # gone from the current view…
    current = (await firm.viewer.get(f"/api/v1/companies/{cid}/registers/members")).json()
    assert current == []
    # …but the FULL history remains, delete event included with its reason
    history = (await firm.viewer.get(f"/api/v1/register-entries/{key}/history")).json()
    assert [h["version"] for h in history] == [1, 2]
    assert history[1]["is_deleted"] is True
    assert history[1]["delete_reason"] == "entered in error"

    # deleted entries cannot be amended (legal record, no resurrection)
    res = await post(firm.manager, f"/register-entries/{key}",
                     {"payload": MEMBER, "expected_version": 2}, method="PUT")
    assert res.status_code == 409


async def test_typed_schema_rejects_missing_and_unknown_fields(firm) -> None:
    cid = await _company(firm)
    res = await post(firm.executive, f"/companies/{cid}/registers/members",
                     {"payload": {"name": "No Folio", "surprise_field": "x"}})
    assert res.status_code == 422
    problems = res.json()["detail"]["problems"]
    assert any("missing required field: folio_no" in p for p in problems)
    assert any("unknown field: surprise_field" in p for p in problems)

    res = await post(firm.executive, f"/companies/{cid}/registers/nonexistent",
                     {"payload": {}})
    assert res.status_code == 404


async def test_as_on_point_in_time_view(firm) -> None:
    cid = await _company(firm)
    key = (
        await post(firm.executive, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    ).json()["entry_key"]
    v1_time = (await firm.viewer.get(
        f"/api/v1/register-entries/{key}/history")).json()[0]["recorded_at"]
    await post(firm.manager, f"/register-entries/{key}",
               {"payload": {**MEMBER, "shares_held": "8000"}, "expected_version": 1},
               method="PUT")

    # as-on the moment v1 was recorded → the extract shows v1's figures
    from urllib.parse import quote

    res = await firm.viewer.get(
        f"/api/v1/companies/{cid}/registers/members?as_on={quote(v1_time)}")
    assert res.json()[0]["payload"]["shares_held"] == "5000"
    # now → v2
    res = await firm.viewer.get(f"/api/v1/companies/{cid}/registers/members")
    assert res.json()[0]["payload"]["shares_held"] == "8000"


async def test_export_carries_as_on_stamp_and_versions(firm) -> None:
    import io

    from openpyxl import load_workbook

    cid = await _company(firm)
    await post(firm.executive, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    res = await firm.viewer.get(f"/api/v1/companies/{cid}/registers/members/export")
    assert res.status_code == 200
    ws = load_workbook(io.BytesIO(res.content)).active
    rows = list(ws.values)
    assert "Register of Members" in rows[0][0] and "as on" in rows[0][0]  # §8 stamp
    header = list(rows[1])
    assert "entry_version" in header
    assert rows[2][header.index("entry_version")] == 1


async def test_registers_rbac_and_tenancy(firm, make_client) -> None:
    cid = await _company(firm)
    res = await post(firm.viewer, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    assert res.status_code == 403

    key = (
        await post(firm.executive, f"/companies/{cid}/registers/members", {"payload": MEMBER})
    ).json()["entry_key"]
    rival = make_client()
    await register_firm(rival, "rival-registers@example.com", "Rival")
    assert (await rival.get(f"/api/v1/companies/{cid}/registers")).status_code == 404
    assert (await rival.get(f"/api/v1/register-entries/{key}/history")).status_code == 404
    res = await post(rival, f"/register-entries/{key}", {"reason": "attack"}, method="DELETE")
    assert res.status_code == 404
