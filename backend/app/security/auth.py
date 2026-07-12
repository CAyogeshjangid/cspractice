"""Password hashing (argon2), JWT cookies, and the RBAC dependency (charter §3, C10)."""
from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from redis.asyncio import Redis

from app.config import get_settings
from app.db import get_session
from app.models import Role, User

_hasher = PasswordHasher()
ACCESS_COOKIE = "praxis_access"
REFRESH_COOKIE = "praxis_refresh"

_redis_client: Redis | None = None


def _redis() -> Redis:
    """Redis-backed token state — no in-memory dicts, ever (charter C4)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client

MIN_PASSWORD_LEN = 12  # strong-password policy (PRD §4.1)


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def make_access_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "firm_id": str(user.firm_id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(minutes=s.access_token_minutes),
            "type": "access",
        },
        s.jwt_secret,
        algorithm="HS256",
    )


def make_refresh_token(user: User) -> tuple[str, str]:
    """Returns (token, jti). The jti is stored in Redis for rotation/revocation."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    token = jwt.encode(
        {
            "sub": str(user.id),
            "jti": jti,
            "iat": now,
            "exp": now + timedelta(days=s.refresh_token_days),
            "type": "refresh",
        },
        s.jwt_secret,
        algorithm="HS256",
    )
    return token, jti


async def store_refresh_jti(jti: str, user_id: uuid.UUID) -> None:
    ttl = get_settings().refresh_token_days * 86400
    await _redis().set(f"refresh:{jti}", str(user_id), ex=ttl)


async def consume_refresh_jti(jti: str) -> str | None:
    """Single-use: GETDEL. A second use of the same jti returns None → 401.
    Rotation means a stolen refresh token dies the moment either party uses it."""
    value = await _redis().getdel(f"refresh:{jti}")
    return str(value) if value is not None else None


async def revoke_refresh_jti(jti: str) -> None:
    await _redis().delete(f"refresh:{jti}")


async def stash_pending_totp(user_id: uuid.UUID, secret: str) -> None:
    """Secret is pending (10 min) until the user proves possession with a code;
    only then does it land on the user row and become enforced at login."""
    await _redis().set(f"totp_pending:{user_id}", secret, ex=600)


async def pop_pending_totp(user_id: uuid.UUID) -> str | None:
    value = await _redis().getdel(f"totp_pending:{user_id}")
    return str(value) if value is not None else None


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    s = get_settings()
    for name, value, max_age in (
        (ACCESS_COOKIE, access, s.access_token_minutes * 60),
        (REFRESH_COOKIE, refresh, s.refresh_token_days * 86400),
    ):
        response.set_cookie(
            name, value, max_age=max_age,
            httponly=True, samesite="lax", secure=s.is_prod, path="/",
        )


def clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/")


async def current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="wrong token type")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    user = (
        await session.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user inactive or unknown")
    return user


_ROLE_ORDER = {Role.viewer: 0, Role.executive: 1, Role.manager: 2, Role.partner: 3}


def require_role(minimum: Role) -> Callable[..., Coroutine[Any, Any, User]]:
    """RBAC dependency used by every route (charter M2). Server-side, per request —
    UI hiding is cosmetic, never the control (PRD §9)."""

    async def _dep(user: User = Depends(current_user)) -> User:
        if _ROLE_ORDER[user.role] < _ROLE_ORDER[minimum]:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return _dep
