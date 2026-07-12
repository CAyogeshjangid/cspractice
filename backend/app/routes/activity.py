"""Activity log view (PRD §4.9 — P0): Partner/Manager visible, filterable.
Read-only by construction; the table itself is INSERT-only at the DB layer."""
from __future__ import annotations

from typing import Any

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Role, User
from app.repositories import activity as repo
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1/activity", tags=["activity"])


@router.get("")
async def list_activity(
    response: Response,
    entity_type: str | None = None,
    action: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(require_role(Role.manager)),  # "View activity log": P/M (PRD §9)
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows, total = await repo.list_activity(
        session,
        user.firm_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
        limit=min(limit, 200),
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "id": str(entry.id),
            "actor_email": email,
            "entity_type": entry.entity_type,
            "entity_id": str(entry.entity_id) if entry.entity_id else None,
            "action": entry.action,
            "diff": entry.diff,
            "ip": entry.ip,
            "created_at": entry.created_at.isoformat(),
        }
        for entry, email in rows
    ]
