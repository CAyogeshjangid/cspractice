from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import Role, User
from app.repositories import companies as companies_repo
from app.repositories import masters as repo
from app.schemas.masters import DirectorIn, DirectorOut, DisclosureIn, DisclosureOut
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1/companies/{company_id}/directors", tags=["directors"])


async def _owned_company(session: AsyncSession, user: User, company_id: uuid.UUID) -> None:
    if await companies_repo.get_company(session, user.firm_id, company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")


@router.get("", response_model=list[DirectorOut])
async def list_directors(
    company_id: uuid.UUID,
    fy: int | None = None,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[DirectorOut]:
    await _owned_company(session, user, company_id)
    rows = await repo.list_directors(session, user.firm_id, company_id, fy=fy)
    return [DirectorOut.model_validate(r) for r in rows]


@router.post("", response_model=DirectorOut, status_code=201)
async def create_director(
    company_id: uuid.UUID,
    body: DirectorIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> DirectorOut:
    await _owned_company(session, user, company_id)
    director = await repo.create_director(session, user.firm_id, company_id, body.model_dump())
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="director",
        entity_id=director.id, action="create", after=body.model_dump(mode="json"),
        request=request,
    )
    await session.commit()
    return DirectorOut.model_validate(director)


@router.put("/{director_id}", response_model=DirectorOut)
async def update_director(
    company_id: uuid.UUID,
    director_id: uuid.UUID,
    body: DirectorIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> DirectorOut:
    await _owned_company(session, user, company_id)
    director = await repo.get_director(session, user.firm_id, director_id)
    if director is None or director.company_id != company_id:
        raise HTTPException(status_code=404, detail="director not found")

    before, after = {}, {}
    for key, value in body.model_dump().items():
        current = getattr(director, key)
        if current != value:
            before[key], after[key] = str(current), str(value)
            setattr(director, key, value)
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="director",
        entity_id=director.id, action="update", before=before, after=after, request=request,
    )
    await session.commit()
    return DirectorOut.model_validate(director)


@router.get("/{director_id}/disclosures", response_model=list[DisclosureOut])
async def list_disclosures(
    company_id: uuid.UUID,
    director_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[DisclosureOut]:
    await _owned_company(session, user, company_id)
    director = await repo.get_director(session, user.firm_id, director_id)
    if director is None or director.company_id != company_id:
        raise HTTPException(status_code=404, detail="director not found")
    return [
        DisclosureOut.model_validate(r)
        for r in await repo.list_disclosures(session, user.firm_id, director_id)
    ]


@router.put("/{director_id}/disclosures/{fy}", response_model=DisclosureOut)
async def upsert_disclosure(
    company_id: uuid.UUID,
    director_id: uuid.UUID,
    fy: int,
    body: DisclosureIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> DisclosureOut:
    await _owned_company(session, user, company_id)
    director = await repo.get_director(session, user.firm_id, director_id)
    if director is None or director.company_id != company_id:
        raise HTTPException(status_code=404, detail="director not found")
    row, before = await repo.upsert_disclosure(
        session, user.firm_id, director_id, fy, body.model_dump()
    )
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="director_disclosure",
        entity_id=row.id, action="update" if before else "create",
        before=before, after=body.model_dump(mode="json"), request=request,
    )
    await session.commit()
    return DisclosureOut.model_validate(row)
