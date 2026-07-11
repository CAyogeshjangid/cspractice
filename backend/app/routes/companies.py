from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import Role, User
from app.repositories import companies as repo
from app.schemas.companies import CompanyIn, CompanyOut, DeleteIn
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
async def list_companies(
    response: Response,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[CompanyOut]:
    rows, total = await repo.list_companies(
        session, user.firm_id, limit=min(limit, 200), offset=offset
    )
    response.headers["X-Total-Count"] = str(total)  # pagination convention (§9)
    return [CompanyOut.model_validate(r) for r in rows]


@router.post("", response_model=CompanyOut, status_code=201)
async def create_company(
    body: CompanyIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),  # Executive+ may create (PRD §9)
    session: AsyncSession = Depends(get_session),
) -> CompanyOut:
    existing = await repo.get_by_cin(session, user.firm_id, body.cin)
    if existing is not None and existing.deleted_at is None:
        raise HTTPException(status_code=409, detail="CIN already exists in this firm")
    if existing is not None:  # soft-deleted: restore-and-update (REVIEW F8)
        before = {"deleted_at": str(existing.deleted_at), "deleted_reason": existing.deleted_reason}
        existing.deleted_at = None
        existing.deleted_reason = None
        for k, v in body.model_dump().items():
            setattr(existing, k, v)
        await session.flush()
        await audit.record(
            session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="company",
            entity_id=existing.id, action="restore", before=before,
            after=body.model_dump(mode="json"), request=request,
        )
        await session.commit()
        return CompanyOut.model_validate(existing)

    company = await repo.create_company(session, user.firm_id, body.model_dump())
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="company",
        entity_id=company.id, action="create", after=body.model_dump(mode="json"), request=request,
    )
    await session.commit()
    return CompanyOut.model_validate(company)


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> CompanyOut:
    company = await repo.get_company(session, user.firm_id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return CompanyOut.model_validate(company)


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: uuid.UUID,
    body: DeleteIn,
    request: Request,
    user: User = Depends(require_role(Role.partner)),  # Partner ONLY; soft delete (PRD §9)
    session: AsyncSession = Depends(get_session),
) -> None:
    company = await repo.soft_delete(session, user.firm_id, company_id, body.reason)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="company",
        entity_id=company.id, action="soft_delete", after={"reason": body.reason}, request=request,
    )
    await session.commit()
