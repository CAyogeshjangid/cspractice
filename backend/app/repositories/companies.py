"""Company repository — ALL access requires firm_id (charter C10).

No route handler builds queries against tenant tables; they call these.
"""
from __future__ import annotations

import uuid
from typing import Any
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company


async def list_companies(
    session: AsyncSession, firm_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> tuple[list[Company], int]:
    base = select(Company).where(Company.firm_id == firm_id, Company.deleted_at.is_(None))
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (await session.execute(base.order_by(Company.name).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return list(rows), total


async def get_company(
    session: AsyncSession, firm_id: uuid.UUID, company_id: uuid.UUID
) -> Company | None:
    return (
        await session.execute(
            select(Company).where(
                Company.firm_id == firm_id,
                Company.id == company_id,
                Company.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def get_by_cin(session: AsyncSession, firm_id: uuid.UUID, cin: str) -> Company | None:
    """Includes soft-deleted rows — re-import of a deleted CIN restores (REVIEW F8)."""
    return (
        await session.execute(
            select(Company).where(Company.firm_id == firm_id, Company.cin == cin)
        )
    ).scalar_one_or_none()


async def create_company(
    session: AsyncSession, firm_id: uuid.UUID, data: dict[str, Any]
) -> Company:
    company = Company(firm_id=firm_id, **data)
    session.add(company)
    await session.flush()
    return company


async def soft_delete(
    session: AsyncSession, firm_id: uuid.UUID, company_id: uuid.UUID, reason: str
) -> Company | None:
    company = await get_company(session, firm_id, company_id)
    if company is None:
        return None
    company.deleted_at = datetime.now(timezone.utc)
    company.deleted_reason = reason
    await session.flush()
    return company
