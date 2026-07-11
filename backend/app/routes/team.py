"""Team management: invitations (Partner only — PRD §9 'team invites').

Invitation-only membership (PRD §4.1): no open signup into an existing firm.
The raw token is returned once to the Partner; email delivery of invitations
arrives with the reminder pipeline (M5). Only its SHA-256 hash is stored.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import Invitation, Role, User
from app.security.auth import (
    hash_password,
    make_access_token,
    make_refresh_token,
    require_role,
    set_auth_cookies,
    store_refresh_jti,
)

router = APIRouter(prefix="/api/v1/team", tags=["team"])

INVITE_TTL_DAYS = 7


class InviteIn(BaseModel):
    email: EmailStr
    role: Role


class AcceptIn(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=12, max_length=200)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/invitations", status_code=201)
async def create_invitation(
    body: InviteIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    email_taken = (
        await session.execute(select(User.id).where(User.email == body.email))
    ).scalar_one_or_none()
    if email_taken:
        raise HTTPException(status_code=409, detail="a user with this email already exists")

    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        firm_id=user.firm_id,
        email=body.email,
        role=body.role,
        token_hash=_hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invitation)
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="invitation",
        entity_id=invitation.id, action="create",
        after={"email": body.email, "role": body.role.value}, request=request,
    )
    await session.commit()
    return {
        "invitation_id": str(invitation.id),
        "token": token,  # shown once; only the hash is stored
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.get("/invitations")
async def list_invitations(
    user: User = Depends(require_role(Role.partner)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, str | None]]:
    rows = (
        (
            await session.execute(
                select(Invitation)
                .where(Invitation.firm_id == user.firm_id)
                .order_by(Invitation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(i.id),
            "email": i.email,
            "role": i.role.value,
            "expires_at": i.expires_at.isoformat(),
            "accepted_at": i.accepted_at.isoformat() if i.accepted_at else None,
        }
        for i in rows
    ]


@router.post("/invitations/accept", status_code=201)
async def accept_invitation(
    body: AcceptIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    invitation = (
        await session.execute(
            select(Invitation).where(Invitation.token_hash == _hash_token(body.token))
        )
    ).scalar_one_or_none()
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(status_code=410, detail="invitation invalid, used, or expired")

    email_taken = (
        await session.execute(select(User.id).where(User.email == invitation.email))
    ).scalar_one_or_none()
    if email_taken:
        raise HTTPException(status_code=409, detail="a user with this email already exists")

    new_user = User(
        firm_id=invitation.firm_id,
        email=invitation.email,
        password_hash=hash_password(body.password),
        role=invitation.role,
    )
    session.add(new_user)
    invitation.accepted_at = datetime.now(timezone.utc)
    await session.flush()
    await audit.record(
        session, firm_id=invitation.firm_id, actor_user_id=new_user.id, entity_type="user",
        entity_id=new_user.id, action="accept_invitation",
        after={"email": new_user.email, "role": new_user.role.value}, request=request,
    )
    await session.commit()

    refresh, jti = make_refresh_token(new_user)
    await store_refresh_jti(jti, new_user.id)
    set_auth_cookies(response, make_access_token(new_user), refresh)
    return {"role": new_user.role.value}
