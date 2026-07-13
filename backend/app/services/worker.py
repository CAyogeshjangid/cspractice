"""arq worker (charter §3: Redis-backed jobs, no in-process timers).

Run: python -m arq app.services.worker.WorkerSettings
Jobs persist in Redis — killing the worker mid-queue loses nothing (M5).
"""
from __future__ import annotations

from typing import Any

import uuid
from datetime import date

from arq import cron
from arq.connections import RedisSettings
from arq.worker import Retry
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.services.reminders import (
    deliver,
    schedule_dsc_reminders,
    schedule_due_reminders,
)

RETRY_BACKOFF_SECONDS = (60, 300, 900)  # 1m, 5m, 15m


async def startup(ctx: dict[str, Any]) -> None:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def send_reminder_job(ctx: dict[str, Any], dispatch_id: str) -> str:
    async with ctx["session_factory"]() as session:
        outcome = await deliver(session, uuid.UUID(dispatch_id), date.today())
    if outcome == "retry":
        attempt = min(ctx.get("job_try", 1), len(RETRY_BACKOFF_SECONDS)) - 1
        raise Retry(defer=RETRY_BACKOFF_SECONDS[attempt])
    return outcome


async def schedule_reminders_job(ctx: dict[str, Any]) -> int:
    """Daily: create due dispatches (calendar + DSC expiry), then enqueue
    anything queued through the shared send path."""
    async with ctx["session_factory"]() as session:
        today = date.today()
        created = await schedule_due_reminders(session, today)
        created += await schedule_dsc_reminders(session, today)

        from sqlalchemy import select

        from app.models import DispatchStatus, ReminderDispatch

        queued = (
            (
                await session.execute(
                    select(ReminderDispatch.id).where(
                        ReminderDispatch.status == DispatchStatus.queued
                    )
                )
            )
            .scalars()
            .all()
        )
    for dispatch_id in queued:
        await ctx["redis"].enqueue_job(
            "send_reminder_job", str(dispatch_id), _job_id=f"dispatch:{dispatch_id}"
        )  # _job_id makes re-enqueueing idempotent while a job is pending
    return created


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [send_reminder_job, schedule_reminders_job]
    cron_jobs = [cron(schedule_reminders_job, hour={1}, minute={30})]  # daily 01:30 UTC
    on_startup = startup
    on_shutdown = shutdown
    # deliver() owns the attempt budget; Retry re-queues with explicit backoff,
    # so arq's own retry counter stays at a high ceiling.
    max_tries = 10


# Resolved when the worker process imports this module (env is present there);
# module import itself stays side-effect-free for tests and tooling.
WorkerSettings.redis_settings = _redis_settings()  # type: ignore[attr-defined]
