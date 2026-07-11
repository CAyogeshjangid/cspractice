"""RBAC matrix tests — one test per implemented PRD §9 row, positive AND
negative (charter M2 acceptance). Rows for modules not yet built (calendar
overrides, templates, activity-log view) are added with their milestones.
"""
from __future__ import annotations

import pytest

from tests.conftest import post

COMPANY = {"cin": "U74999MH2020PTC123456", "name": "Fixture Pvt Ltd"}


async def _create_company(client) -> str:
    res = await post(client, "/companies", COMPANY)
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --- Row: "Create/edit entities & masters — Partner ✔ Manager ✔ Executive ✔ Viewer ✘"

@pytest.mark.parametrize("persona", ["partner", "manager", "executive"])
async def test_create_company_allowed(firm, persona) -> None:
    res = await post(getattr(firm, persona), "/companies", COMPANY)
    assert res.status_code == 201, f"{persona}: {res.text}"


async def test_viewer_cannot_create_company(firm) -> None:
    res = await post(firm.viewer, "/companies", COMPANY)
    assert res.status_code == 403


# --- Row: "Delete entity (soft) — Partner ✔, everyone else ✘"

async def test_partner_can_soft_delete(firm) -> None:
    company_id = await _create_company(firm.partner)
    res = await post(firm.partner, f"/companies/{company_id}", {"reason": "test cleanup"},
                     method="DELETE")
    assert res.status_code == 204


@pytest.mark.parametrize("persona", ["manager", "executive", "viewer"])
async def test_non_partner_cannot_delete(firm, persona) -> None:
    """Includes the charter's named negative case: Executive cannot delete → 403."""
    company_id = await _create_company(firm.partner)
    res = await post(getattr(firm, persona), f"/companies/{company_id}",
                     {"reason": "should be denied"}, method="DELETE")
    assert res.status_code == 403, f"{persona} must not delete companies"
    # and the company is still there
    still = await getattr(firm, persona).get(f"/api/v1/companies/{company_id}")
    assert still.status_code == 200


# --- Row: "Firm settings, billing, team invites — Partner only"

async def test_partner_can_invite(firm) -> None:
    res = await post(firm.partner, "/team/invitations",
                     {"email": "new@example.com", "role": "executive"})
    assert res.status_code == 201


@pytest.mark.parametrize("persona", ["manager", "executive", "viewer"])
async def test_non_partner_cannot_invite_or_list_invitations(firm, persona) -> None:
    client = getattr(firm, persona)
    res = await post(client, "/team/invitations", {"email": "x@example.com", "role": "viewer"})
    assert res.status_code == 403
    res = await client.get("/api/v1/team/invitations")
    assert res.status_code == 403


# --- Row: "Read everything in scope — all roles ✔"

@pytest.mark.parametrize("persona", ["partner", "manager", "executive", "viewer"])
async def test_all_roles_can_read(firm, persona) -> None:
    company_id = await _create_company(firm.partner)
    client = getattr(firm, persona)
    assert (await client.get("/api/v1/companies")).status_code == 200
    assert (await client.get(f"/api/v1/companies/{company_id}")).status_code == 200


# --- TOTP is a Partner capability (PRD §4.1)

@pytest.mark.parametrize("persona", ["manager", "executive", "viewer"])
async def test_non_partner_cannot_setup_totp(firm, persona) -> None:
    res = await post(getattr(firm, persona), "/auth/totp/setup", {})
    assert res.status_code == 403


# --- Unauthenticated requests are rejected outright

async def test_unauthenticated_gets_401(firm) -> None:
    anon = firm.make_client()
    assert (await anon.get("/api/v1/companies")).status_code == 401
    assert (await post(anon, "/companies", COMPANY)).status_code == 401
