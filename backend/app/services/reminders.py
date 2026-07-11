"""Reminder scheduling and dispatch (charter M5).

- schedule_due_reminders: idempotent — one dispatch per (config, scheduled
  date); re-running never duplicates. Rows already filed / not-applicable are
  skipped. Missing recipients → dispatch created DEAD immediately (visible in
  the dead-letter view; silent failure is a defect, PRD §4.6).
- deliver: MAX_ATTEMPTS total tries (initial + 3 retries with backoff handled
  by the arq worker); exhausted → status dead.
- No date computation beyond subtracting the reminder offset from the stored
  effective due date (C12: due dates come only from the rules engine).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CalendarRow,
    Company,
    DispatchStatus,
    Firm,
    ReminderConfig,
    ReminderDispatch,
    RowStatus,
    RuleExtension,
    User,
)
from app.services.email import EmailPayload, send_email

MAX_ATTEMPTS = 4  # 1 initial + 3 retries → then dead-letter (M5 acceptance)
TERMINAL_ROW_STATUSES = {RowStatus.filed, RowStatus.not_applicable}


def _effective_due(row: CalendarRow, extension_date: date | None) -> date | None:
    return row.override_date or extension_date or row.computed_due_date


async def schedule_due_reminders(session: AsyncSession, today: date) -> int:
    """Create queued dispatches for every reminder whose send-day has arrived.
    Catch-up included: a missed send-day still dispatches while the due date
    is in the future. Returns number of dispatches created."""
    pairs = (
        await session.execute(
            select(ReminderConfig, CalendarRow, RuleExtension)
            .join(CalendarRow, ReminderConfig.calendar_row_id == CalendarRow.id)
            .outerjoin(RuleExtension, CalendarRow.extension_id == RuleExtension.id)
        )
    ).all()

    created = 0
    for config, row, ext in pairs:
        if row.status in TERMINAL_ROW_STATUSES:
            continue
        due = _effective_due(row, ext.extended_due_date if ext else None)
        if due is None or due < today:
            continue
        existing = {
            d.scheduled_for
            for d in (
                await session.execute(
                    select(ReminderDispatch).where(
                        ReminderDispatch.reminder_config_id == config.id
                    )
                )
            ).scalars()
        }
        for days in config.days_before:
            send_day = due - timedelta(days=days)
            if send_day <= today and send_day not in existing:
                session.add(
                    ReminderDispatch(
                        firm_id=config.firm_id,
                        reminder_config_id=config.id,
                        scheduled_for=send_day,
                        status=DispatchStatus.queued,
                    )
                )
                created += 1
    await session.commit()
    return created


async def deliver(session: AsyncSession, dispatch_id: uuid.UUID, today: date) -> str:
    """Attempt one delivery. Returns 'sent' | 'retry' | 'dead' | 'skipped'.
    The arq worker maps 'retry' to a deferred re-run with backoff."""
    dispatch = (
        await session.execute(
            select(ReminderDispatch).where(ReminderDispatch.id == dispatch_id)
        )
    ).scalar_one_or_none()
    if dispatch is None or dispatch.status in (DispatchStatus.sent, DispatchStatus.dead):
        return "skipped"

    config = (
        await session.execute(
            select(ReminderConfig).where(ReminderConfig.id == dispatch.reminder_config_id)
        )
    ).scalar_one()
    row = (
        await session.execute(
            select(CalendarRow).where(CalendarRow.id == config.calendar_row_id)
        )
    ).scalar_one()
    if row.status in TERMINAL_ROW_STATUSES:
        dispatch.status = DispatchStatus.dead
        dispatch.error = "row resolved before dispatch"
        await session.commit()
        return "dead"

    recipients = list(config.extra_emails or [])
    if row.assignee_user_id:
        assignee_email = (
            await session.execute(select(User.email).where(User.id == row.assignee_user_id))
        ).scalar_one_or_none()
        if assignee_email:
            recipients.insert(0, assignee_email)
    if not recipients:
        dispatch.status = DispatchStatus.dead
        dispatch.error = "no recipients (no assignee, no extra emails)"
        await session.commit()
        return "dead"

    firm = (
        await session.execute(select(Firm).where(Firm.id == dispatch.firm_id))
    ).scalar_one()
    company_name = (
        await session.execute(select(Company.name).where(Company.id == row.company_id))
    ).scalar_one()
    ext_date = None
    if row.extension_id:
        ext_date = (
            await session.execute(
                select(RuleExtension.extended_due_date).where(
                    RuleExtension.id == row.extension_id
                )
            )
        ).scalar_one_or_none()
    due = _effective_due(row, ext_date)

    payload = EmailPayload(
        to=recipients,
        subject=f"[Praxis] Compliance due {due}: {company_name}",
        body=(
            f"Company: {company_name}\n"
            f"Due date: {due}\n"
            f"Status: {row.status.value}\n"
            f"SRN: {row.srn or '—'}\n"
            f"Remarks: {row.remarks or '—'}\n\n"
            "This reminder was generated by Praxis from your firm's compliance "
            "calendar. Dates trace to the versioned rules dataset."
        ),
    )
    try:
        provider = await send_email(firm.settings, payload)
    except Exception as exc:
        dispatch.attempt_count += 1
        dispatch.error = str(exc)[:500]
        if dispatch.attempt_count >= MAX_ATTEMPTS:
            dispatch.status = DispatchStatus.dead
            await session.commit()
            return "dead"
        dispatch.status = DispatchStatus.failed
        await session.commit()
        return "retry"

    dispatch.status = DispatchStatus.sent
    dispatch.sent_at = today
    dispatch.provider = provider
    dispatch.attempt_count += 1
    dispatch.error = None
    await session.commit()
    return "sent"
