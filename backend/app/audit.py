"""Activity-log helper (charter C11) — every mutating endpoint records an entry.

INSERT-only: the application DB role has no UPDATE/DELETE grant on activity_log
(enforced in the initial migration), and this module exposes no update path.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models import ActivityLog


async def record(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    session.add(
        ActivityLog(
            firm_id=firm_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            diff={"before": before, "after": after},
            ip=request.client.host if request and request.client else None,
        )
    )
