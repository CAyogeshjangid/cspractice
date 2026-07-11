"""Activity log reads — firm_id required (C10). Write path is app/audit.py;
there is deliberately no update/delete function in either module (C11)."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityLog, User


async def list_activity(
    session: AsyncSession,
    firm_id: uuid.UUID,
    *,
    entity_type: str | None = None,
    action: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[ActivityLog, str | None]], int]:
    """→ ([(entry, actor_email)], total). Filterable per PRD §4.9."""
    q = (
        select(ActivityLog, User.email)
        .outerjoin(User, ActivityLog.actor_user_id == User.id)
        .where(ActivityLog.firm_id == firm_id)
    )
    if entity_type:
        q = q.where(ActivityLog.entity_type == entity_type)
    if action:
        q = q.where(ActivityLog.action == action)
    if entity_id:
        q = q.where(ActivityLog.entity_id == entity_id)
    if actor_user_id:
        q = q.where(ActivityLog.actor_user_id == actor_user_id)
    if date_from:
        q = q.where(func.date(ActivityLog.created_at) >= date_from)
    if date_to:
        q = q.where(func.date(ActivityLog.created_at) <= date_to)

    total = (
        await session.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            q.order_by(ActivityLog.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return [(entry, email) for entry, email in rows], total
