from __future__ import annotations

from typing import Any

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import Role, User
from app.repositories import companies as companies_repo
from app.repositories import masters as repo
from app.schemas.masters import ShareholderIn, ShareholderOut
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1/companies/{company_id}/shareholders", tags=["shareholders"])

PERCENT_TOLERANCE = Decimal("0.5")  # warn when totals drift beyond ±0.5% (PRD §4.4)


async def _owned_company(session: AsyncSession, user: User, company_id: uuid.UUID) -> None:
    if await companies_repo.get_company(session, user.firm_id, company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")


@router.get("")
async def list_shareholders(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _owned_company(session, user, company_id)
    rows = await repo.list_shareholders(session, user.firm_id, company_id)
    total_shares = sum((r.shares or 0) for r in rows)
    total_pct = sum((r.percentage or 0) for r in rows)
    return {
        "shareholders": [ShareholderOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total_shares": str(total_shares),
        "total_percentage": str(total_pct),
        # warning, not an error: cap tables are legitimately incomplete mid-entry
        "percentage_warning": bool(rows) and abs(Decimal(total_pct) - 100) > PERCENT_TOLERANCE,
    }


@router.post("", response_model=ShareholderOut, status_code=201)
async def create_shareholder(
    company_id: uuid.UUID,
    body: ShareholderIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> ShareholderOut:
    await _owned_company(session, user, company_id)
    row = await repo.create_shareholder(session, user.firm_id, company_id, body.model_dump())
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="shareholder",
        entity_id=row.id, action="create", after=body.model_dump(mode="json"), request=request,
    )
    await session.commit()
    return ShareholderOut.model_validate(row)


@router.put("/{shareholder_id}", response_model=ShareholderOut)
async def update_shareholder(
    company_id: uuid.UUID,
    shareholder_id: uuid.UUID,
    body: ShareholderIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> ShareholderOut:
    await _owned_company(session, user, company_id)
    row = await repo.get_shareholder(session, user.firm_id, shareholder_id)
    if row is None or row.company_id != company_id:
        raise HTTPException(status_code=404, detail="shareholder not found")

    before, after = {}, {}
    for key, value in body.model_dump().items():
        current = getattr(row, key)
        if current != value:
            before[key], after[key] = str(current), str(value)
            setattr(row, key, value)
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="shareholder",
        entity_id=row.id, action="update", before=before, after=after, request=request,
    )
    await session.commit()
    return ShareholderOut.model_validate(row)
