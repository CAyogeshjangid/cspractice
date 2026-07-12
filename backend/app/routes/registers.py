"""Statutory registers routes (PRD Phase 2 / §8). Append-only end to end."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import RegisterEntry, RegisterType, Role, User
from app.repositories import companies as companies_repo
from app.security.auth import require_role
from app.services import registers as svc

router = APIRouter(prefix="/api/v1", tags=["registers"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class EntryIn(BaseModel):
    payload: dict[str, Any]


class AmendIn(BaseModel):
    payload: dict[str, Any]
    expected_version: int = Field(ge=1)


class DeleteIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


async def _owned_company(session: AsyncSession, user: User, company_id: uuid.UUID) -> None:
    if await companies_repo.get_company(session, user.firm_id, company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")


def _register_type(value: str) -> RegisterType:
    try:
        return RegisterType(value)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"unknown register type: {value}")


def _entry_out(e: RegisterEntry) -> dict[str, Any]:
    return {
        "entry_key": str(e.entry_key),
        "version": e.version_no,
        "payload": e.payload,
        "is_deleted": e.is_deleted,
        "delete_reason": e.delete_reason,
        "recorded_at": e.created_at.isoformat(),
    }


@router.get("/companies/{company_id}/registers")
async def registers_summary(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """All 14 registers with their section refs, schemas, and entry counts —
    including not-yet-started ones, so nothing is invisible."""
    await _owned_company(session, user, company_id)
    count_rows = (
        await session.execute(
            select(RegisterEntry.register_type, func.count(func.distinct(RegisterEntry.entry_key)))
            .where(
                RegisterEntry.firm_id == user.firm_id,
                RegisterEntry.company_id == company_id,
            )
            .group_by(RegisterEntry.register_type)
        )
    ).all()
    counts: dict[RegisterType, int] = {rtype: n for rtype, n in count_rows}
    return [
        {
            "type": rtype.value,
            "name": spec.name,
            "section": spec.section,
            "mandatory": spec.mandatory,
            "required_fields": list(spec.required),
            "optional_fields": list(spec.optional),
            "entries": counts.get(rtype, 0),
        }
        for rtype, spec in svc.REGISTERS.items()
    ]


@router.get("/companies/{company_id}/registers/{register_type}")
async def list_entries(
    company_id: uuid.UUID,
    register_type: str,
    as_on: datetime | None = None,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    await _owned_company(session, user, company_id)
    rows = await svc.entries_as_on(
        session, user.firm_id, company_id, _register_type(register_type), as_on
    )
    return [_entry_out(e) for e in rows]


@router.post("/companies/{company_id}/registers/{register_type}", status_code=201)
async def create_entry(
    company_id: uuid.UUID,
    register_type: str,
    body: EntryIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _owned_company(session, user, company_id)
    rtype = _register_type(register_type)
    try:
        entry = await svc.create_entry(
            session, user.firm_id, company_id, rtype, body.payload, user.id
        )
    except svc.PayloadInvalid as exc:
        raise HTTPException(status_code=422, detail={"title": "invalid entry", "problems": exc.problems})
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="register_entry",
        entity_id=entry.id, action="create",
        after={"register": rtype.value, "entry_key": str(entry.entry_key)}, request=request,
    )
    await session.commit()
    return _entry_out(entry)


@router.put("/register-entries/{entry_key}")
async def amend_entry(
    entry_key: uuid.UUID,
    body: AmendIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        entry = await svc.amend_entry(
            session, user.firm_id, entry_key, body.payload, body.expected_version, user.id
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="entry not found")
    except svc.VersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except svc.PayloadInvalid as exc:
        raise HTTPException(status_code=422, detail={"title": "invalid entry", "problems": exc.problems})
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="register_entry",
        entity_id=entry.id, action="amend",
        after={"entry_key": str(entry_key), "new_version": entry.version_no}, request=request,
    )
    await session.commit()
    return _entry_out(entry)


@router.delete("/register-entries/{entry_key}")
async def delete_entry(
    entry_key: uuid.UUID,
    body: DeleteIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),  # legal records: Partner only
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        entry = await svc.soft_delete_entry(session, user.firm_id, entry_key, body.reason, user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="entry not found")
    except svc.VersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="register_entry",
        entity_id=entry.id, action="soft_delete",
        after={"entry_key": str(entry_key), "reason": body.reason}, request=request,
    )
    await session.commit()
    return _entry_out(entry)


@router.get("/register-entries/{entry_key}/history")
async def entry_history(
    entry_key: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = await svc.history(session, user.firm_id, entry_key)
    if not rows:
        raise HTTPException(status_code=404, detail="entry not found")
    return [_entry_out(e) for e in rows]


@router.get("/companies/{company_id}/registers/{register_type}/export")
async def export_register(
    company_id: uuid.UUID,
    register_type: str,
    as_on: datetime | None = None,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Excel extract stamped with the as-on date and per-row versions (§8)."""
    await _owned_company(session, user, company_id)
    rtype = _register_type(register_type)
    spec = svc.REGISTERS[rtype]
    rows = await svc.entries_as_on(session, user.firm_id, company_id, rtype, as_on)

    wb = Workbook()
    ws = wb.active
    ws.title = rtype.value[:31]
    stamp_time = as_on or datetime.now(timezone.utc)
    ws.append([f"{spec.name} ({spec.section}) — as on {stamp_time.isoformat(timespec='seconds')}"])
    fields = list(spec.fields)
    ws.append([*fields, "entry_version", "recorded_at"])
    for e in rows:
        ws.append([
            *[str(e.payload.get(f, "")) for f in fields],
            e.version_no,
            e.created_at.isoformat(timespec="seconds"),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{rtype.value}_register.xlsx"'},
    )
