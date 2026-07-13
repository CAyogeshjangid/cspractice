"""Firm settings (Partner only — PRD §9). Email provider config is stored
encrypted; secrets never appear in responses or logs (C8)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.services.reminders import DSC_SETTINGS_KEY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import Firm, Role, User
from app.security.auth import require_role
from app.security.crypto import encrypt_secret

router = APIRouter(prefix="/api/v1/firm", tags=["firm"])


class EmailSettingsIn(BaseModel):
    provider: Literal["smtp", "resend"]
    from_addr: EmailStr
    # smtp
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    # resend
    api_key: str | None = None


@router.put("/email-settings")
async def put_email_settings(
    body: EmailSettingsIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if body.provider == "smtp" and not (body.host and body.port):
        raise HTTPException(status_code=422, detail="smtp requires host and port")
    if body.provider == "resend" and not body.api_key:
        raise HTTPException(status_code=422, detail="resend requires an api_key")

    config: dict[str, Any] = {"provider": body.provider, "from_addr": body.from_addr}
    if body.provider == "smtp":
        config.update({"host": body.host, "port": body.port, "use_tls": body.use_tls})
        if body.username:
            config["username"] = body.username
        if body.password:
            config["password_enc"] = encrypt_secret(body.password)
    else:
        config["api_key_enc"] = encrypt_secret(body.api_key or "")

    firm = (await session.execute(select(Firm).where(Firm.id == user.firm_id))).scalar_one()
    firm.settings = {**(firm.settings or {}), "email": config}
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="firm",
        entity_id=firm.id, action="email_settings_update",
        after={"provider": body.provider, "from_addr": body.from_addr},  # never secrets
        request=request,
    )
    await session.commit()
    return await get_email_settings(user, session)


class DscReminderSettingsIn(BaseModel):
    """Firm-level DSC certificate-expiry reminder policy (M18). Recipients are
    an explicit firm list — DSC tokens have no per-token owner to fall back on."""

    days_before: list[int] = Field(default_factory=list, max_length=10)
    recipients: list[EmailStr] = Field(default_factory=list, max_length=10)


@router.put("/dsc-reminders")
async def put_dsc_reminders(
    body: DscReminderSettingsIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if any(d < 0 or d > 365 for d in body.days_before):
        raise HTTPException(status_code=422, detail="days_before values must be 0–365")
    days = sorted({int(d) for d in body.days_before}, reverse=True)
    recipients = [str(r) for r in body.recipients]
    firm = (await session.execute(select(Firm).where(Firm.id == user.firm_id))).scalar_one()
    config = {"days_before": days, "recipients": recipients}
    firm.settings = {**(firm.settings or {}), DSC_SETTINGS_KEY: config}
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="firm",
        entity_id=firm.id, action="dsc_reminders_update", after=config, request=request,
    )
    await session.commit()
    return config


@router.get("/dsc-reminders")
async def get_dsc_reminders(
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    firm = (await session.execute(select(Firm).where(Firm.id == user.firm_id))).scalar_one()
    config = (firm.settings or {}).get(DSC_SETTINGS_KEY) or {}
    return {
        "days_before": config.get("days_before", []),
        "recipients": config.get("recipients", []),
    }


@router.get("/email-settings")
async def get_email_settings(
    user: User = Depends(require_role(Role.partner)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    firm = (await session.execute(select(Firm).where(Firm.id == user.firm_id))).scalar_one()
    config = (firm.settings or {}).get("email") or {}
    return {
        "provider": config.get("provider"),
        "from_addr": config.get("from_addr"),
        "host": config.get("host"),
        "port": config.get("port"),
        "username": config.get("username"),
        "use_tls": config.get("use_tls"),
        "has_password": "password_enc" in config,  # presence flags only (C8)
        "has_api_key": "api_key_enc" in config,
    }
