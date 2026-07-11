"""Activity log view (PRD §4.9): P/M only, firm-scoped, filterable."""
from __future__ import annotations

from tests.conftest import post, register_firm

COMPANY = {"cin": "U74999MH2020PTC121212", "name": "Audit Trail Co"}


async def test_partner_and_manager_see_filterable_trail(firm) -> None:
    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    await post(firm.executive, f"/companies/{cid}", {"agm_date": "2026-09-30"}, method="PUT")

    res = await firm.partner.get("/api/v1/activity")
    assert res.status_code == 200
    actions = [e["action"] for e in res.json()]
    assert "create" in actions and "update" in actions and "register" in actions
    assert int(res.headers["X-Total-Count"]) >= len(actions)

    # diffs carry before/after; actor is resolved to an email
    update = next(e for e in res.json() if e["action"] == "update")
    assert update["diff"]["after"] == {"agm_date": "2026-09-30"}
    assert update["actor_email"] == "executive@example.com"

    # filters narrow correctly
    res = await firm.manager.get(f"/api/v1/activity?entity_type=company&entity_id={cid}")
    assert {e["entity_type"] for e in res.json()} == {"company"}
    assert all(e["entity_id"] == cid for e in res.json())
    res = await firm.manager.get("/api/v1/activity?action=create&entity_type=company")
    assert [e["action"] for e in res.json()] == ["create"]


async def test_executive_and_viewer_cannot_see_activity(firm) -> None:
    """PRD §9: View activity log is Partner/Manager only."""
    assert (await firm.executive.get("/api/v1/activity")).status_code == 403
    assert (await firm.viewer.get("/api/v1/activity")).status_code == 403


async def test_activity_is_firm_scoped(firm, make_client) -> None:
    await post(firm.manager, "/companies", COMPANY)
    rival = make_client()
    await register_firm(rival, "rival-activity@example.com", "Rival")
    res = await rival.get("/api/v1/activity")
    assert res.status_code == 200
    # rival sees only its own registration event, nothing from the other firm
    assert {e["action"] for e in res.json()} == {"register"}
