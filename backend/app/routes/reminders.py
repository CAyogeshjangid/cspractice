"""Reminder configuration + dispatch visibility (charter M5, PRD §4.6)."""
from __future__ import annotations

from typing import Any

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import (
    DispatchStatus,
    ReminderConfig,
    ReminderDispatch,
    Role,
    User,
)
from app.repositories import calendar as cal_repo
from app.security.auth import require_role

router = APIRouter(prefix="/api/v1", tags=["reminders"])


class ReminderIn(BaseModel):
    days_before: list[int] = Field(min_length=1, max_length=10)
    extra_emails: list[EmailStr] = Field(default_factory=list, max_length=10)


@router.put("/calendar-rows/{row_id}/reminders")
async def upsert_reminder(
    row_id: uuid.UUID,
    body: ReminderIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if any(d < 0 or d > 120 for d in body.days_before):
        raise HTTPException(status_code=422, detail="days_before values must be 0–120")
    row = await cal_repo.get_row(session, user.firm_id, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="calendar row not found")
    if user.role == Role.executive and row.assignee_user_id != user.id:
        raise HTTPException(status_code=403, detail="executives may edit assigned rows only")

    config = (
        await session.execute(
            select(ReminderConfig).where(ReminderConfig.calendar_row_id == row_id)
        )
    ).scalar_one_or_none()
    days = sorted(set(body.days_before), reverse=True)
    if config is None:
        config = ReminderConfig(
            firm_id=user.firm_id, calendar_row_id=row_id,
            days_before=days, extra_emails=list(body.extra_emails),
        )
        session.add(config)
        action, before = "create", None
    else:
        before = {"days_before": config.days_before, "extra_emails": config.extra_emails}
        config.days_before = days
        config.extra_emails = list(body.extra_emails)
        action = "update"
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="reminder_config",
        entity_id=config.id, action=action, before=before,
        after={"days_before": days, "extra_emails": list(body.extra_emails)}, request=request,
    )
    await session.commit()
    return {"days_before": config.days_before, "extra_emails": config.extra_emails}


@router.get("/calendar-rows/{row_id}/reminders")
async def get_reminder(
    row_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await cal_repo.get_row(session, user.firm_id, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="calendar row not found")
    config = (
        await session.execute(
            select(ReminderConfig).where(ReminderConfig.calendar_row_id == row_id)
        )
    ).scalar_one_or_none()
    if config is None:
        return {"days_before": [], "extra_emails": []}
    return {"days_before": config.days_before, "extra_emails": config.extra_emails}


@router.get("/reminders/dead-letter")
async def dead_letter_view(
    user: User = Depends(require_role(Role.manager)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Failed + dead dispatches for the firm — silent failure is a defect (§4.6)."""
    rows = (
        (
            await session.execute(
                select(ReminderDispatch)
                .where(
                    ReminderDispatch.firm_id == user.firm_id,
                    ReminderDispatch.status.in_(
                        [DispatchStatus.failed, DispatchStatus.dead]
                    ),
                )
                .order_by(ReminderDispatch.updated_at.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(d.id),
            "scheduled_for": d.scheduled_for.isoformat(),
            "status": d.status.value,
            "attempt_count": d.attempt_count,
            "error": d.error,
        }
        for d in rows
    ]


@router.post("/reminders/{dispatch_id}/retry")
async def retry_dispatch(
    dispatch_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_role(Role.manager)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    dispatch = (
        await session.execute(
            select(ReminderDispatch).where(
                ReminderDispatch.firm_id == user.firm_id,
                ReminderDispatch.id == dispatch_id,
            )
        )
    ).scalar_one_or_none()
    if dispatch is None:
        raise HTTPException(status_code=404, detail="dispatch not found")
    if dispatch.status == DispatchStatus.sent:
        raise HTTPException(status_code=409, detail="dispatch already sent")

    dispatch.status = DispatchStatus.queued
    dispatch.attempt_count = 0  # fresh attempt budget after human intervention
    dispatch.error = None
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="reminder_dispatch",
        entity_id=dispatch.id, action="manual_retry", request=request,
    )
    await session.commit()
    # picked up by the worker's next scheduling sweep (queued → enqueue)
    return {"status": "queued"}
