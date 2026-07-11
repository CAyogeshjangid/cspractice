"""Auth lifecycle integration tests: rotation, revocation, invitations, TOTP.

Hit real Postgres + Redis (charter §8: no mocked DB/queues).
"""
from __future__ import annotations

import pyotp

from tests.conftest import STRONG_PW, post, register_firm


async def test_refresh_rotation_single_use(make_client) -> None:
    client = make_client()
    await register_firm(client, "rotate@example.com")
    old_refresh = client.cookies.get("praxis_refresh")

    res = await post(client, "/auth/refresh", {})
    assert res.status_code == 200
    assert client.cookies.get("praxis_refresh") != old_refresh  # rotated

    # replaying the consumed token must fail (single-use jti)
    client.cookies.set("praxis_refresh", old_refresh)
    res = await post(client, "/auth/refresh", {})
    assert res.status_code == 401


async def test_logout_revokes_refresh(make_client) -> None:
    client = make_client()
    await register_firm(client, "logout@example.com")
    refresh = client.cookies.get("praxis_refresh")

    res = await post(client, "/auth/logout", {})
    assert res.status_code == 204

    client.cookies.set("praxis_refresh", refresh)
    res = await post(client, "/auth/refresh", {})
    assert res.status_code == 401  # jti deleted server-side, not just cookie cleared


async def test_invitation_lifecycle(make_client) -> None:
    partner = make_client()
    await register_firm(partner, "inviter@example.com")
    res = await post(partner, "/team/invitations", {"email": "m@example.com", "role": "manager"})
    token = res.json()["token"]

    # accept: creates the user with the invited role, in the inviter's firm
    joiner = make_client()
    res = await post(joiner, "/team/invitations/accept", {"token": token, "password": STRONG_PW})
    assert res.status_code == 201
    assert res.json()["role"] == "manager"
    assert (await joiner.get("/api/v1/companies")).status_code == 200  # logged in

    # the token is single-use
    second = make_client()
    res = await post(second, "/team/invitations/accept", {"token": token, "password": STRONG_PW})
    assert res.status_code == 410

    # a bogus token is rejected without leaking anything
    res = await post(second, "/team/invitations/accept",
                     {"token": "x" * 43, "password": STRONG_PW})
    assert res.status_code == 410


async def test_totp_setup_enable_and_login_enforcement(make_client) -> None:
    partner = make_client()
    await register_firm(partner, "totp@example.com")

    # setup → pending secret; wrong code → 400 and still pending
    res = await post(partner, "/auth/totp/setup", {})
    secret = res.json()["secret"]
    assert "otpauth://" in res.json()["otpauth_uri"]
    res = await post(partner, "/auth/totp/enable", {"code": "000000"})
    assert res.status_code == 400
    res = await post(partner, "/auth/totp/enable", {"code": pyotp.TOTP(secret).now()})
    assert res.status_code == 204

    # fresh session: password alone is no longer enough
    fresh = make_client()
    res = await post(fresh, "/auth/login", {"email": "totp@example.com", "password": STRONG_PW})
    assert res.status_code == 401
    assert res.json()["detail"] == "totp_required"

    res = await post(fresh, "/auth/login", {
        "email": "totp@example.com", "password": STRONG_PW,
        "totp_code": pyotp.TOTP(secret).now(),
    })
    assert res.status_code == 200
    assert res.json()["role"] == "partner"


async def test_wrong_password_is_401(make_client) -> None:
    client = make_client()
    await register_firm(client, "pw@example.com")
    fresh = make_client()
    res = await post(fresh, "/auth/login",
                     {"email": "pw@example.com", "password": "wrong-password-123"})
    assert res.status_code == 401


async def test_duplicate_registration_is_opaque_409(make_client) -> None:
    client = make_client()
    await register_firm(client, "dupe@example.com")
    other = make_client()
    res = await post(other, "/auth/register",
                     {"firm_name": "Other", "email": "dupe@example.com", "password": STRONG_PW})
    assert res.status_code == 409
    assert "dupe@example.com" not in res.text  # no user enumeration


async def test_audit_trail_captures_auth_events(make_client) -> None:
    client = make_client()
    await register_firm(client, "audit@example.com")

    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ActivityLog

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        actions = (await session.execute(select(ActivityLog.action))).scalars().all()
    assert "register" in actions
