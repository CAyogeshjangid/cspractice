"""Practice masters routes: auditors (+appointments), PCS, DSC tokens (M11)."""
from __future__ import annotations

from typing import Any

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import (
    Auditor,
    AuditorAppointment,
    DscToken,
    PcsProfessional,
    Role,
    User,
)
from app.repositories import companies as companies_repo
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1", tags=["practice-masters"])


# ---------- auditors ----------

class AuditorIn(BaseModel):
    firm_name: str = Field(min_length=2, max_length=200)
    frn: str = Field(min_length=3, max_length=20)
    address: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


@router.get("/auditors")
async def list_auditors(
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(Auditor).where(Auditor.firm_id == user.firm_id).order_by(Auditor.firm_name)
            )
        )
        .scalars()
        .all()
    )
    return [
        {"id": str(a.id), "firm_name": a.firm_name, "frn": a.frn, "address": a.address,
         "email": a.email, "phone": a.phone}
        for a in rows
    ]


@router.post("/auditors", status_code=201)
async def create_auditor(
    body: AuditorIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    auditor = Auditor(firm_id=user.firm_id, **body.model_dump())
    session.add(auditor)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="an auditor with this FRN already exists")
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="auditor",
        entity_id=auditor.id, action="create", after=body.model_dump(mode="json"),
        request=request,
    )
    await session.commit()
    return {"id": str(auditor.id)}


class AppointmentIn(BaseModel):
    auditor_id: uuid.UUID
    appointed_from_fy: int
    appointed_to_fy: int | None = None
    adt1_srn: str | None = None
    remarks: str | None = None


@router.get("/companies/{company_id}/auditor-appointments")
async def list_appointments(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    if await companies_repo.get_company(session, user.firm_id, company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")
    rows = (
        await session.execute(
            select(AuditorAppointment, Auditor.firm_name, Auditor.frn)
            .join(Auditor, AuditorAppointment.auditor_id == Auditor.id)
            .where(
                AuditorAppointment.firm_id == user.firm_id,
                AuditorAppointment.company_id == company_id,
            )
            .order_by(AuditorAppointment.appointed_from_fy.desc())
        )
    ).all()
    return [
        {
            "id": str(a.id), "auditor_id": str(a.auditor_id), "auditor_name": name,
            "frn": frn, "appointed_from_fy": a.appointed_from_fy,
            "appointed_to_fy": a.appointed_to_fy, "adt1_srn": a.adt1_srn,
            "current": a.appointed_to_fy is None,
        }
        for a, name, frn in rows
    ]


@router.post("/companies/{company_id}/auditor-appointments", status_code=201)
async def create_appointment(
    company_id: uuid.UUID,
    body: AppointmentIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if await companies_repo.get_company(session, user.firm_id, company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")
    auditor = (
        await session.execute(
            select(Auditor).where(Auditor.firm_id == user.firm_id, Auditor.id == body.auditor_id)
        )
    ).scalar_one_or_none()
    if auditor is None:
        raise HTTPException(status_code=404, detail="auditor not found")
    appointment = AuditorAppointment(firm_id=user.firm_id, company_id=company_id,
                                     **body.model_dump())
    session.add(appointment)
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="auditor_appointment",
        entity_id=appointment.id, action="create",
        after={"auditor": auditor.firm_name, "from_fy": body.appointed_from_fy},
        request=request,
    )
    await session.commit()
    return {"id": str(appointment.id)}


# ---------- PCS ----------

class PcsIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    membership_no: str = Field(min_length=1, max_length=20)
    cop_no: str | None = None
    firm_name: str | None = None
    address: str | None = None
    email: EmailStr | None = None


@router.get("/pcs")
async def list_pcs(
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(PcsProfessional)
                .where(PcsProfessional.firm_id == user.firm_id)
                .order_by(PcsProfessional.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        {"id": str(p.id), "name": p.name, "membership_no": p.membership_no,
         "cop_no": p.cop_no, "firm_name": p.firm_name, "email": p.email}
        for p in rows
    ]


@router.post("/pcs", status_code=201)
async def create_pcs(
    body: PcsIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    pcs = PcsProfessional(firm_id=user.firm_id, **body.model_dump())
    session.add(pcs)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="this membership number already exists")
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="pcs_professional",
        entity_id=pcs.id, action="create", after=body.model_dump(mode="json"), request=request,
    )
    await session.commit()
    return {"id": str(pcs.id)}


# ---------- DSC tokens ----------

class DscIn(BaseModel):
    holder_name: str = Field(min_length=2, max_length=200)
    director_id: uuid.UUID | None = None
    token_color: str | None = None
    token_number: str | None = None
    expiry_date: date | None = None
    remarks: str | None = None


@router.get("/dsc-tokens")
async def list_dsc(
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(DscToken)
                .where(DscToken.firm_id == user.firm_id)
                .order_by(DscToken.expiry_date.nulls_last())
            )
        )
        .scalars()
        .all()
    )
    # expiry math stays out of routes (C12 discipline) — the UI compares dates
    return [
        {"id": str(t.id), "holder_name": t.holder_name,
         "director_id": str(t.director_id) if t.director_id else None,
         "token_color": t.token_color, "token_number": t.token_number,
         "expiry_date": str(t.expiry_date) if t.expiry_date else None,
         "remarks": t.remarks}
        for t in rows
    ]


@router.post("/dsc-tokens", status_code=201)
async def create_dsc(
    body: DscIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    token = DscToken(firm_id=user.firm_id, **body.model_dump())
    session.add(token)
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="dsc_token",
        entity_id=token.id, action="create",
        after={"holder": body.holder_name, "expiry": str(body.expiry_date)}, request=request,
    )
    await session.commit()
    return {"id": str(token.id)}


@router.put("/dsc-tokens/{token_id}")
async def update_dsc(
    token_id: uuid.UUID,
    body: DscIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    token = (
        await session.execute(
            select(DscToken).where(DscToken.firm_id == user.firm_id, DscToken.id == token_id)
        )
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=404, detail="token not found")
    before, after = {}, {}
    for key, value in body.model_dump().items():
        current = getattr(token, key)
        if current != value:
            before[key], after[key] = str(current), str(value)
            setattr(token, key, value)
    if after:
        await audit.record(
            session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="dsc_token",
            entity_id=token.id, action="update", before=before, after=after, request=request,
        )
        await session.commit()
    return {"id": str(token.id)}
