"""M5-carryover (M7 hardening): the REAL arq worker consumes a REAL Redis
queue end-to-end — enqueue → burst worker run → dispatch sent."""
from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import post

FY = 2026
DUE = date(2026, 10, 30)


async def test_arq_worker_processes_enqueued_dispatch(firm, tmp_path, monkeypatch) -> None:
    # fixture: company + rule + calendar row + reminder config + queued dispatch
    import app.db as dbmod
    from app.rules.load import load_entries
    from app.rules.loader import load_dataset_files
    from app.services.reminders import schedule_due_reminders

    (tmp_path / "rules.yaml").write_text(
        "- code: TEST-ONLY-WORKER\n  category: roc\n  obligation_name: Worker fixture\n"
        "  effective_from: 2025-04-01\n  anchor: agm_date\n"
        "  offset_spec: {type: offset, unit: days, amount: 30}\n"
        "  source_citation: TEST-ONLY\n"
    )
    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        await load_entries(session, load_dataset_files(tmp_path, allow_test_only=True))
    cid = (await post(firm.manager, "/companies", {
        "cin": "U74999MH2020PTC202020", "name": "Worker Fixture", "agm_date": "2026-09-30",
    })).json()["id"]
    await post(firm.manager, f"/companies/{cid}/calendar/generate?fy={FY}", {})
    row_id = (await firm.manager.get(
        f"/api/v1/companies/{cid}/calendar?fy={FY}")).json()[0]["id"]
    await post(firm.manager, f"/calendar-rows/{row_id}/reminders",
               {"days_before": [30], "extra_emails": ["ops@example.com"]}, method="PUT")

    today = DUE - timedelta(days=30)
    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        assert await schedule_due_reminders(session, today) == 1

    from sqlalchemy import select

    from app.models import DispatchStatus, ReminderDispatch

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        dispatch = (await session.execute(select(ReminderDispatch))).scalars().one()

    # provider stubbed at the service seam; queue + worker are fully real
    sent = []

    async def fake_send(firm_settings, payload):
        sent.append(payload)
        return "smtp"

    monkeypatch.setattr("app.services.reminders.send_email", fake_send)

    # enqueue on the REAL Redis queue, then run the REAL worker in burst mode
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    from app.config import get_settings
    from app.services.worker import send_reminder_job, shutdown, startup

    settings = RedisSettings.from_dsn(get_settings().redis_url)
    pool = await create_pool(settings)
    await pool.enqueue_job("send_reminder_job", str(dispatch.id))

    worker = Worker(
        functions=[send_reminder_job],
        redis_settings=settings,
        on_startup=startup,
        on_shutdown=shutdown,
        burst=True,          # drain the queue, then exit — deterministic in tests
        poll_delay=0.1,
    )
    await worker.main()
    await worker.close()
    await pool.aclose()

    assert len(sent) == 1
    assert sent[0].to == ["ops@example.com"]
    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        dispatch = (await session.execute(select(ReminderDispatch))).scalars().one()
    assert dispatch.status == DispatchStatus.sent
    assert dispatch.provider == "smtp"
