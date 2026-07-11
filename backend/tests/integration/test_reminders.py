"""M5 acceptance: idempotent scheduling, retry×3 → dead-letter, dead-letter
visibility, dispatch logging, encrypted provider config."""
from __future__ import annotations

from datetime import date, timedelta


from tests.conftest import post

FY = 2026
RULESET = """
- code: TEST-ONLY-REMIND
  category: roc
  obligation_name: Reminder fixture obligation
  effective_from: 2025-04-01
  anchor: agm_date
  offset_spec: {type: offset, unit: days, amount: 30}
  source_citation: TEST-ONLY
"""
COMPANY = {
    "cin": "U74999MH2020PTC777777",
    "name": "Reminder Fixture Pvt Ltd",
    "agm_date": "2026-09-30",  # due = 2026-10-30
}
DUE = date(2026, 10, 30)


async def setup_row(firm, tmp_path) -> tuple[str, str]:
    """→ (company_id, calendar_row_id) with the fixture rule generated."""
    import app.db as dbmod
    from app.rules.load import load_entries
    from app.rules.loader import load_dataset_files

    (tmp_path / "rules.yaml").write_text(RULESET)
    entries = load_dataset_files(tmp_path, allow_test_only=True)
    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        await load_entries(session, entries)

    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    await post(firm.manager, f"/companies/{cid}/calendar/generate?fy={FY}", {})
    rows = (await firm.manager.get(f"/api/v1/companies/{cid}/calendar?fy={FY}")).json()
    return cid, rows[0]["id"]


async def run_scheduler(today: date) -> int:
    import app.db as dbmod
    from app.services.reminders import schedule_due_reminders

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return await schedule_due_reminders(session, today)


async def run_deliver(dispatch_id, today: date) -> str:
    import app.db as dbmod
    from app.services.reminders import deliver

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return await deliver(session, dispatch_id, today)


async def dispatches() -> list:
    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ReminderDispatch

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return list((await session.execute(select(ReminderDispatch))).scalars().all())


async def test_scheduling_is_idempotent_and_date_correct(firm, tmp_path) -> None:
    _cid, row_id = await setup_row(firm, tmp_path)
    res = await post(firm.manager, f"/calendar-rows/{row_id}/reminders",
                     {"days_before": [30, 7], "extra_emails": ["ops@example.com"]},
                     method="PUT")
    assert res.status_code == 200

    today = DUE - timedelta(days=30)  # exactly the 30-day mark
    assert await run_scheduler(today) == 1
    assert await run_scheduler(today) == 0  # idempotent re-run

    rows = await dispatches()
    assert len(rows) == 1
    assert rows[0].scheduled_for == today

    # a week later, the 7-day reminder becomes due; still no duplicates
    assert await run_scheduler(DUE - timedelta(days=7)) == 1
    assert await run_scheduler(DUE - timedelta(days=7)) == 0


async def test_catchup_and_terminal_row_skip(firm, tmp_path) -> None:
    _cid, row_id = await setup_row(firm, tmp_path)
    await post(firm.manager, f"/calendar-rows/{row_id}/reminders",
               {"days_before": [30], "extra_emails": ["ops@example.com"]}, method="PUT")

    # missed the 30-day mark by 3 days → catch-up dispatch still created
    assert await run_scheduler(DUE - timedelta(days=27)) == 1

    # filed rows never remind
    await post(firm.manager, f"/calendar-rows/{row_id}",
               {"status": "filed", "srn": "T0001"}, method="PATCH")
    assert await run_scheduler(DUE - timedelta(days=7)) == 0


async def test_delivery_success_records_provider_and_log(firm, tmp_path, monkeypatch) -> None:
    _cid, row_id = await setup_row(firm, tmp_path)
    await post(firm.manager, f"/calendar-rows/{row_id}/reminders",
               {"days_before": [30], "extra_emails": ["ops@example.com"]}, method="PUT")
    today = DUE - timedelta(days=30)
    await run_scheduler(today)
    dispatch_id = (await dispatches())[0].id

    sent = []

    async def fake_send(firm_settings, payload):
        sent.append(payload)
        return "smtp"

    monkeypatch.setattr("app.services.reminders.send_email", fake_send)
    assert await run_deliver(dispatch_id, today) == "sent"

    d = (await dispatches())[0]
    assert (d.status.value, d.provider, d.attempt_count) == ("sent", "smtp", 1)
    assert d.sent_at == today
    assert sent[0].to == ["ops@example.com"]
    assert "2026-10-30" in sent[0].subject

    # sent dispatches are not re-delivered
    assert await run_deliver(dispatch_id, today) == "skipped"


async def test_failing_provider_retries_3x_then_dead_letter(firm, tmp_path, monkeypatch) -> None:
    """M5 acceptance: 1 initial + 3 retries → dead, visible in the UI view."""
    _cid, row_id = await setup_row(firm, tmp_path)
    await post(firm.manager, f"/calendar-rows/{row_id}/reminders",
               {"days_before": [30], "extra_emails": ["ops@example.com"]}, method="PUT")
    today = DUE - timedelta(days=30)
    await run_scheduler(today)
    dispatch_id = (await dispatches())[0].id

    async def boom(firm_settings, payload):
        raise ConnectionError("smtp unreachable")

    monkeypatch.setattr("app.services.reminders.send_email", boom)
    assert await run_deliver(dispatch_id, today) == "retry"   # attempt 1
    assert await run_deliver(dispatch_id, today) == "retry"   # attempt 2
    assert await run_deliver(dispatch_id, today) == "retry"   # attempt 3
    assert await run_deliver(dispatch_id, today) == "dead"    # attempt 4 → dead

    view = (await firm.manager.get("/api/v1/reminders/dead-letter")).json()
    assert len(view) == 1
    assert view[0]["status"] == "dead"
    assert view[0]["attempt_count"] == 4
    assert "smtp unreachable" in view[0]["error"]

    # executives don't see the dead-letter admin view
    res = await firm.executive.get("/api/v1/reminders/dead-letter")
    assert res.status_code == 403

    # manual retry resets the attempt budget and requeues
    res = await post(firm.manager, f"/reminders/{dispatch_id}/retry", {})
    assert res.status_code == 200
    d = (await dispatches())[0]
    assert (d.status.value, d.attempt_count) == ("queued", 0)


async def test_no_recipients_goes_straight_to_dead_letter(firm, tmp_path) -> None:
    """Silent failure is a defect (PRD §4.6): no assignee + no extras = visible."""
    _cid, row_id = await setup_row(firm, tmp_path)
    await post(firm.manager, f"/calendar-rows/{row_id}/reminders",
               {"days_before": [30]}, method="PUT")
    today = DUE - timedelta(days=30)
    await run_scheduler(today)
    dispatch_id = (await dispatches())[0].id

    assert await run_deliver(dispatch_id, today) == "dead"
    view = (await firm.manager.get("/api/v1/reminders/dead-letter")).json()
    assert "no recipients" in view[0]["error"]


async def test_email_settings_encrypted_and_masked(firm) -> None:
    res = await post(firm.partner, "/firm/email-settings", {
        "provider": "smtp", "from_addr": "praxis@firm.example", "host": "mail.example",
        "port": 587, "username": "mailer", "password": "super-secret-smtp-pass",
    }, method="PUT")
    assert res.status_code == 200
    body = res.json()
    assert body["has_password"] is True
    assert "super-secret-smtp-pass" not in res.text  # never echoed (C8)

    # stored encrypted, decryptable, and absent from the audit log
    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ActivityLog, Firm
    from app.security.crypto import decrypt_secret

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        firm_row = (await session.execute(select(Firm))).scalars().first()
        stored = firm_row.settings["email"]["password_enc"]
        assert stored != "super-secret-smtp-pass"
        assert decrypt_secret(stored) == "super-secret-smtp-pass"
        logs = (await session.execute(select(ActivityLog))).scalars().all()
        assert all("super-secret-smtp-pass" not in str(entry.diff) for entry in logs)

    # Partner-only (PRD §9 firm settings)
    res = await post(firm.manager, "/firm/email-settings", {
        "provider": "resend", "from_addr": "x@example.com", "api_key": "k" * 20,
    }, method="PUT")
    assert res.status_code == 403


async def test_reminder_config_rbac(firm, tmp_path) -> None:
    _cid, row_id = await setup_row(firm, tmp_path)
    res = await post(firm.viewer, f"/calendar-rows/{row_id}/reminders",
                     {"days_before": [7]}, method="PUT")
    assert res.status_code == 403
    # executive on an unassigned row
    res = await post(firm.executive, f"/calendar-rows/{row_id}/reminders",
                     {"days_before": [7]}, method="PUT")
    assert res.status_code == 403