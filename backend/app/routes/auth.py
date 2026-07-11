"""Auth routes: CSRF bootstrap, registration (first user = Partner), login, refresh.

No seeded accounts anywhere (charter C2). Registration creates a NEW firm and
its Partner; additional users join by invitation only (PRD §4.1).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.config import get_settings
from app.db import get_session
from app.models import Firm, Role, User
from app.security.auth import (
    hash_password,
    make_access_token,
    make_refresh_token,
    set_auth_cookies,
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

    refresh, _jti = make_refresh_token(user)
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

    refresh, _jti = make_refresh_token(user)
    set_auth_cookies(response, make_access_token(user), refresh)
    return {"role": user.role.value}
