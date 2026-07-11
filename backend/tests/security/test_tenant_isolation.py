"""Cross-tenant tests for every implemented endpoint (charter C10).

Firm B must not be able to read, mutate, or even confirm the existence of
Firm A's data — cross-tenant lookups return 404 (not 403, which would leak
existence).
"""
from __future__ import annotations

from tests.conftest import post, register_firm


async def _two_firms(make_client):
    a = make_client()
    await register_firm(a, "firm-a@example.com", "Firm A")
    b = make_client()
    await register_firm(b, "firm-b@example.com", "Firm B")
    res = await post(a, "/companies", {"cin": "U11111MH2020PTC111111", "name": "A's Company"})
    return a, b, res.json()["id"]


async def test_cross_tenant_read_is_404(make_client) -> None:
    _a, b, company_id = await _two_firms(make_client)
    assert (await b.get(f"/api/v1/companies/{company_id}")).status_code == 404


async def test_cross_tenant_delete_is_404_and_harmless(make_client) -> None:
    a, b, company_id = await _two_firms(make_client)
    res = await post(b, f"/companies/{company_id}", {"reason": "malicious"}, method="DELETE")
    assert res.status_code == 404
    assert (await a.get(f"/api/v1/companies/{company_id}")).status_code == 200


async def test_list_is_scoped_to_own_firm(make_client) -> None:
    _a, b, _cid = await _two_firms(make_client)
    res = await b.get("/api/v1/companies")
    assert res.status_code == 200
    assert res.json() == []
    assert res.headers["X-Total-Count"] == "0"


async def test_same_cin_allowed_in_different_firms(make_client) -> None:
    """CIN uniqueness is per-firm, not global — two firms can serve one client."""
    a, b, _cid = await _two_firms(make_client)
    res = await post(b, "/companies", {"cin": "U11111MH2020PTC111111", "name": "B's view"})
    assert res.status_code == 201
    # while a duplicate within the SAME firm is a 409
    dup = await post(a, "/companies", {"cin": "U11111MH2020PTC111111", "name": "dup"})
    assert dup.status_code == 409


async def test_invitations_scoped_to_firm(make_client) -> None:
    a, b, _cid = await _two_firms(make_client)
    await post(a, "/team/invitations", {"email": "colleague@example.com", "role": "manager"})
    assert (await b.get("/api/v1/team/invitations")).json() == []
