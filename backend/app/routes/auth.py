"""Auth routes: CSRF bootstrap, registration (first user = Partner), login, refresh.

No seeded accounts anywhere (charter C2). Registration creates a NEW firm and
its Partner; additional users join by invitation only (PRD §4.1).
"""
from __future__ import annotations

import uuid

import jwt as pyjwt
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.config import get_settings
from app.db import get_session
from app.models import Firm, Role, User
from app.security.auth import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    consume_refresh_jti,
    hash_password,
    make_access_token,
    make_refresh_token,
    pop_pending_totp,
    require_role,
    revoke_refresh_jti,
    set_auth_cookies,
    stash_pending_totp,
    store_refresh_jti,
    verify_password,
)
from app.security.csrf import COOKIE_NAME as CSRF_COOKIE
from app.security.csrf import issue_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterIn(BaseModel):
    firm_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class TotpEnableIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.get("/csrf")
async def get_csrf(response: Response) -> dict[str, str]:
    """Issue the CSRF cookie. Clients echo it in X-CSRF-Token on mutations (C3)."""
    s = get_settings()
    token = issue_token(s.csrf_secret)
    response.set_cookie(
        CSRF_COOKIE, token, httponly=False, samesite="lax", secure=s.is_prod, path="/"
    )
    return {"csrf_token": token}


@router.post("/register", status_code=201)
async def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    existing = (
        await session.execute(select(func.count()).select_from(User).where(User.email == body.email))
    ).scalar_one()
    if existing:
        # same body as success-shaped errors elsewhere; do not leak which emails exist
        raise HTTPException(status_code=409, detail="registration could not be completed")

    firm = Firm(name=body.firm_name)
    session.add(firm)
    await session.flush()
    user = User(
        firm_id=firm.id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=Role.partner,  # first user of a firm is its Partner
    )
    session.add(user)
    await session.flush()
    await audit.record(
        session,
        firm_id=firm.id,
        actor_user_id=user.id,
        entity_type="firm",
        entity_id=firm.id,
        action="register",
        after={"firm_name": firm.name, "partner_email": user.email},
        request=request,
    )
    await session.commit()

    refresh, jti = make_refresh_token(user)
    await store_refresh_jti(jti, user.id)
    set_auth_cookies(response, make_access_token(user), refresh)
    return {"firm_id": str(firm.id), "role": user.role.value}


@router.post("/login")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    user = (
        await session.execute(select(User).where(User.email == body.email, User.is_active))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    if user.totp_secret:  # 2FA enforced once enabled (PRD §4.1)
        if body.totp_code is None:
            raise HTTPException(status_code=401, detail="totp_required")
        if not pyotp.TOTP(user.totp_secret).verify(body.totp_code, valid_window=1):
            raise HTTPException(status_code=401, detail="invalid credentials")

    await audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="login",
        request=request,
    )
    await session.commit()

    refresh, jti = make_refresh_token(user)
    await store_refresh_jti(jti, user.id)
    set_auth_cookies(response, make_access_token(user), refresh)
    return {"role": user.role.value}


@router.post("/refresh")
async def refresh_tokens(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Rotating refresh: each token is single-use (Redis GETDEL). Reuse of a
    consumed token — by the owner or a thief — is rejected."""
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="no refresh token")
    try:
        payload = pyjwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="wrong token type")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    user_id = await consume_refresh_jti(payload["jti"])
    if user_id is None or user_id != payload["sub"]:
        raise HTTPException(status_code=401, detail="refresh token revoked or already used")

    user = (
        await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user inactive or unknown")

    new_refresh, jti = make_refresh_token(user)
    await store_refresh_jti(jti, user.id)
    set_auth_cookies(response, make_access_token(user), new_refresh)
    return {"role": user.role.value}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            payload = pyjwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
            await revoke_refresh_jti(payload.get("jti", ""))
        except pyjwt.InvalidTokenError:
            pass  # cookie is cleared regardless
    clear_auth_cookies(response)


@router.post("/totp/setup")
async def totp_setup(user: User = Depends(require_role(Role.partner))) -> dict[str, str]:
    """Generate a pending TOTP secret (Partner only). Enforced at login only
    after /totp/enable proves the authenticator has it."""
    secret = pyotp.random_base32()
    await stash_pending_totp(user.id, secret)
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Praxis")
    return {"otpauth_uri": uri, "secret": secret}


@router.post("/totp/enable", status_code=204)
async def totp_enable(
    body: TotpEnableIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),
    session: AsyncSession = Depends(get_session),
) -> None:
    secret = await pop_pending_totp(user.id)
    if secret is None:
        raise HTTPException(status_code=409, detail="no pending TOTP setup (expired?)")
    if not pyotp.TOTP(secret).verify(body.code, valid_window=1):
        await stash_pending_totp(user.id, secret)  # keep pending for a retry
        raise HTTPException(status_code=400, detail="invalid TOTP code")

    db_user = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
    db_user.totp_secret = secret
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="user",
        entity_id=user.id, action="totp_enabled", request=request,
    )
    await session.commit()
