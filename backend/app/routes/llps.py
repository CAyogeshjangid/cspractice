"""LLP routes: masters, partners, Form 11/8 working papers (M13)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import (
    Llp,
    LlpForm,
    LlpPartner,
    LlpWorkingPaper,
    Role,
    User,
    WorkingPaperStatus,
)
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1", tags=["llps"])

# Typed working-paper schemas (same validation philosophy as registers):
# drafted in-house from the forms' data requirements; refined in review.
FORM_SCHEMAS: dict[LlpForm, dict[str, tuple[str, ...]]] = {
    LlpForm.form11: {
        "required": ("total_contribution_received",),
        "optional": ("penalties_or_compounding_details", "remarks"),
    },
    LlpForm.form8: {
        "required": ("turnover", "assets_total", "liabilities_total"),
        "optional": ("other_income", "expenditure", "profit_or_loss",
                     "solvency_declared", "charges_outstanding", "remarks"),
    },
}


class LlpIn(BaseModel):
    llpin: str = Field(min_length=7, max_length=10)
    name: str = Field(min_length=1, max_length=300)
    incorporation_date: date | None = None
    registered_address: str | None = None
    email: str | None = None
    phone: str | None = None
    fy_end_month: int = Field(default=3, ge=1, le=12)
    fy_end_day: int = Field(default=31, ge=1, le=31)
    total_contribution: Decimal | None = None


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dpin: str | None = Field(default=None, min_length=8, max_length=8)
    is_designated: bool = False
    appointment_date: date | None = None
    cessation_date: date | None = None
    contribution: Decimal | None = None
    profit_share_percent: Decimal | None = Field(default=None, ge=0, le=100)


class WorkingPaperIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    status: WorkingPaperStatus = WorkingPaperStatus.draft
    srn: str | None = Field(default=None, max_length=50)


class DeleteIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _llp_out(llp: Llp) -> dict:
    return {
        "id": str(llp.id), "llpin": llp.llpin, "name": llp.name,
        "incorporation_date": str(llp.incorporation_date) if llp.incorporation_date else None,
        "registered_address": llp.registered_address, "email": llp.email,
        "fy_end_month": llp.fy_end_month, "fy_end_day": llp.fy_end_day,
        "total_contribution": float(llp.total_contribution) if llp.total_contribution else None,
    }


async def _owned_llp(session: AsyncSession, user: User, llp_id: uuid.UUID) -> Llp:
    llp = (
        await session.execute(
            select(Llp).where(
                Llp.firm_id == user.firm_id, Llp.id == llp_id, Llp.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if llp is None:
        raise HTTPException(status_code=404, detail="LLP not found")
    return llp


@router.get("/llps")
async def list_llps(
    response: Response,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    base = select(Llp).where(Llp.firm_id == user.firm_id, Llp.deleted_at.is_(None))
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.order_by(Llp.name))).scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return [_llp_out(x) for x in rows]


@router.post("/llps", status_code=201)
async def create_llp(
    body: LlpIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    existing = (
        await session.execute(
            select(Llp).where(
                Llp.firm_id == user.firm_id, Llp.llpin == body.llpin, Llp.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="LLPIN already exists in this firm")
    llp = Llp(firm_id=user.firm_id, **body.model_dump())
    session.add(llp)
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="llp",
        entity_id=llp.id, action="create", after=body.model_dump(mode="json"), request=request,
    )
    await session.commit()
    return _llp_out(llp)


@router.get("/llps/{llp_id}")
async def get_llp(
    llp_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return _llp_out(await _owned_llp(session, user, llp_id))


@router.put("/llps/{llp_id}")
async def update_llp(
    llp_id: uuid.UUID,
    body: LlpIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    llp = await _owned_llp(session, user, llp_id)
    before, after = {}, {}
    for key, value in body.model_dump().items():
        current = getattr(llp, key)
        if current != value:
            before[key], after[key] = str(current), str(value)
            setattr(llp, key, value)
    if after:
        await audit.record(
            session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="llp",
            entity_id=llp.id, action="update", before=before, after=after, request=request,
        )
        await session.commit()
    return _llp_out(llp)


@router.delete("/llps/{llp_id}", status_code=204)
async def delete_llp(
    llp_id: uuid.UUID,
    body: DeleteIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),  # soft delete, Partner only
    session: AsyncSession = Depends(get_session),
) -> None:
    llp = await _owned_llp(session, user, llp_id)
    llp.deleted_at = datetime.now(timezone.utc)
    llp.deleted_reason = body.reason
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="llp",
        entity_id=llp.id, action="soft_delete", after={"reason": body.reason}, request=request,
    )
    await session.commit()


# ---------- partners ----------

@router.get("/llps/{llp_id}/partners")
async def list_partners(
    llp_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _owned_llp(session, user, llp_id)
    rows = (
        (
            await session.execute(
                select(LlpPartner)
                .where(LlpPartner.firm_id == user.firm_id, LlpPartner.llp_id == llp_id)
                .order_by(LlpPartner.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(p.id), "name": p.name, "dpin": p.dpin,
            "is_designated": p.is_designated,
            "appointment_date": str(p.appointment_date) if p.appointment_date else None,
            "cessation_date": str(p.cessation_date) if p.cessation_date else None,
            "contribution": float(p.contribution) if p.contribution else None,
            "profit_share_percent": float(p.profit_share_percent)
            if p.profit_share_percent else None,
        }
        for p in rows
    ]


@router.post("/llps/{llp_id}/partners", status_code=201)
async def create_partner(
    llp_id: uuid.UUID,
    body: PartnerIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _owned_llp(session, user, llp_id)
    partner = LlpPartner(firm_id=user.firm_id, llp_id=llp_id, **body.model_dump())
    session.add(partner)
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="llp_partner",
        entity_id=partner.id, action="create", after=body.model_dump(mode="json"),
        request=request,
    )
    await session.commit()
    return {"id": str(partner.id)}


# ---------- Form 11 / Form 8 working papers ----------

def _validate_payload(form: LlpForm, payload: dict[str, Any]) -> None:
    schema = FORM_SCHEMAS[form]
    fields = schema["required"] + schema["optional"]
    problems = [
        f"missing required field: {f}"
        for f in schema["required"]
        if not str(payload.get(f, "")).strip()
    ]
    problems += [f"unknown field: {k}" for k in payload if k not in fields]
    if problems:
        raise HTTPException(status_code=422, detail={"title": "invalid working paper",
                                                     "problems": problems})


@router.get("/llps/{llp_id}/working-papers/{fy}/{form}")
async def get_working_paper(
    llp_id: uuid.UUID,
    fy: int,
    form: LlpForm,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _owned_llp(session, user, llp_id)
    paper = (
        await session.execute(
            select(LlpWorkingPaper).where(
                LlpWorkingPaper.firm_id == user.firm_id,
                LlpWorkingPaper.llp_id == llp_id,
                LlpWorkingPaper.fy == fy,
                LlpWorkingPaper.form == form,
            )
        )
    ).scalar_one_or_none()
    partners = (
        await session.execute(
            select(LlpPartner).where(
                LlpPartner.firm_id == user.firm_id, LlpPartner.llp_id == llp_id
            )
        )
    ).scalars().all()
    active = [p for p in partners if p.cessation_date is None]
    schema = FORM_SCHEMAS[form]
    return {
        "fy": fy,
        "form": form.value,
        "status": paper.status.value if paper else "draft",
        "srn": paper.srn if paper else None,
        "payload": paper.payload if paper else {},
        "required_fields": list(schema["required"]),
        "optional_fields": list(schema["optional"]),
        # server-derived facts the form needs — always from the partners master
        "partner_count": len(active),
        "designated_partner_count": sum(1 for p in active if p.is_designated),
    }


@router.put("/llps/{llp_id}/working-papers/{fy}/{form}")
async def upsert_working_paper(
    llp_id: uuid.UUID,
    fy: int,
    form: LlpForm,
    body: WorkingPaperIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _owned_llp(session, user, llp_id)
    _validate_payload(form, body.payload)
    if body.status == WorkingPaperStatus.finalized and not body.srn:
        raise HTTPException(status_code=422, detail="finalising requires the filing SRN")

    paper = (
        await session.execute(
            select(LlpWorkingPaper).where(
                LlpWorkingPaper.firm_id == user.firm_id,
                LlpWorkingPaper.llp_id == llp_id,
                LlpWorkingPaper.fy == fy,
                LlpWorkingPaper.form == form,
            )
        )
    ).scalar_one_or_none()
    if paper is None:
        paper = LlpWorkingPaper(
            firm_id=user.firm_id, llp_id=llp_id, fy=fy, form=form,
            payload=body.payload, status=body.status, srn=body.srn,
        )
        session.add(paper)
        action, before = "create", None
    else:
        if paper.status == WorkingPaperStatus.finalized:
            raise HTTPException(status_code=409, detail="finalised working papers are read-only")
        before = {"payload": paper.payload, "status": paper.status.value}
        paper.payload = body.payload
        paper.status = body.status
        paper.srn = body.srn
        action = "update"
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="llp_working_paper",
        entity_id=paper.id, action=action, before=before,
        after={"fy": fy, "form": form.value, "status": body.status.value, "srn": body.srn},
        request=request,
    )
    await session.commit()
    return {"status": paper.status.value, "srn": paper.srn}
