"""User-extensible taxonomies: professional groups and industries (PRD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import Role, User
from app.repositories import masters as repo
from app.schemas.masters import TaxonomyIn, TaxonomyOut
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1/taxonomies", tags=["taxonomies"])

Kind = Path(pattern="^(professional-groups|industries)$")


@router.get("/{kind}", response_model=list[TaxonomyOut])
async def list_taxonomy(
    kind: str = Kind,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[TaxonomyOut]:
    return [
        TaxonomyOut.model_validate(r) for r in await repo.list_taxonomy(session, user.firm_id, kind)
    ]


@router.post("/{kind}", response_model=TaxonomyOut, status_code=201)
async def create_taxonomy(
    body: TaxonomyIn,
    request: Request,
    kind: str = Kind,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> TaxonomyOut:
    try:
        row = await repo.create_taxonomy(session, user.firm_id, kind, body.name)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"{kind[:-1]} already exists")
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type=kind,
        entity_id=row.id, action="create", after={"name": body.name}, request=request,
    )
    await session.commit()
    return TaxonomyOut.model_validate(row)
