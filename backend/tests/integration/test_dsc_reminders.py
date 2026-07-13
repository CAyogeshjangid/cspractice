"""M18: DSC certificate-expiry reminders through the shared M5 dispatch
pipeline — firm policy, idempotent scheduling, delivery, dead-letter."""
from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import post

EXPIRY = date(2026, 12, 31)


async def _token(firm, expiry: str = "2026-12-31") -> str:
    res = await post(firm.manager, "/dsc-tokens", {
        "holder_name": "Asha Mehta", "token_color": "epass", "token_number": "T-900",
        "expiry_date": expiry,
    })
    assert res.status_code == 201
    return res.json()["id"]


async def _set_policy(firm, days_before, recipients) -> None:
    res = await post(firm.partner, "/firm/dsc-reminders",
                     {"days_before": days_before, "recipients": recipients}, method="PUT")
    assert res.status_code == 200


async def run_dsc_scheduler(today: date) -> int:
    import app.db as dbmod
    from app.services.reminders import schedule_dsc_reminders

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return await schedule_dsc_reminders(session, today)


async def run_deliver(dispatch_id, today: date) -> str:
    import app.db as dbmod
    from app.services.reminders import deliver

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return await deliver(session, dispatch_id, today)


async def dsc_dispatches() -> list:
    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ReminderDispatch

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return list(
            (
                await session.execute(
                    select(ReminderDispatch).where(
                        ReminderDispatch.subject_kind == "dsc_token"
                    )
                )
            )
            .scalars()
            .all()
        )


async def test_no_policy_means_no_reminders(firm) -> None:
    await _token(firm)
    # a firm that never set a DSC policy gets nothing scheduled
    assert await run_dsc_scheduler(EXPIRY - timedelta(days=30)) == 0
    assert await dsc_dispatches() == []


async def test_scheduling_idempotent_and_date_correct(firm) -> None:
    await _token(firm)
    await _set_policy(firm, [30, 7], ["compliance@firm.example"])

    thirty = EXPIRY - timedelta(days=30)
    assert await run_dsc_scheduler(thirty) == 1
    assert await run_dsc_scheduler(thirty) == 0  # idempotent

    rows = await dsc_dispatches()
    assert len(rows) == 1
    assert rows[0].scheduled_for == thirty
    assert rows[0].dsc_token_id is not None
    assert rows[0].reminder_config_id is None  # not a calendar dispatch

    # the 7-day mark arrives later — still no duplicates
    assert await run_dsc_scheduler(EXPIRY - timedelta(days=7)) == 1
    assert await run_dsc_scheduler(EXPIRY - timedelta(days=7)) == 0


async def test_expired_token_not_scheduled(firm) -> None:
    await _token(firm, expiry="2026-01-01")
    await _set_policy(firm, [30], ["compliance@firm.example"])
    # today is past expiry → no reminder (we don't chase already-lapsed certs)
    assert await run_dsc_scheduler(date(2026, 6, 1)) == 0


async def test_delivery_sends_to_firm_recipients(firm, monkeypatch) -> None:
    await _token(firm)
    await _set_policy(firm, [30], ["compliance@firm.example", "cs@firm.example"])
    today = EXPIRY - timedelta(days=30)
    await run_dsc_scheduler(today)
    dispatch_id = (await dsc_dispatches())[0].id

    sent = []

    async def fake_send(firm_settings, payload):
        sent.append(payload)
        return "smtp"

    monkeypatch.setattr("app.services.reminders.send_email", fake_send)
    assert await run_deliver(dispatch_id, today) == "sent"
    assert sent[0].to == ["compliance@firm.example", "cs@firm.example"]
    assert "DSC expiring 2026-12-31" in sent[0].subject
    assert "Asha Mehta" in sent[0].subject
    # already-sent dispatches are never re-delivered
    assert await run_deliver(dispatch_id, today) == "skipped"


async def test_no_recipients_dead_letters_visibly(firm) -> None:
    """Policy with days but no recipients: silent failure is a defect (§4.6)."""
    await _token(firm)
    await _set_policy(firm, [30], [])
    today = EXPIRY - timedelta(days=30)
    await run_dsc_scheduler(today)
    dispatch_id = (await dsc_dispatches())[0].id

    assert await run_deliver(dispatch_id, today) == "dead"
    view = (await firm.manager.get("/api/v1/reminders/dead-letter")).json()
    dsc = [v for v in view if v["subject_kind"] == "dsc_token"]
    assert len(dsc) == 1
    assert dsc[0]["subject_label"] == "Asha Mehta"
    assert "no recipients" in dsc[0]["error"]


async def test_policy_is_partner_only(firm) -> None:
    res = await post(firm.manager, "/firm/dsc-reminders",
                     {"days_before": [30], "recipients": ["x@firm.example"]}, method="PUT")
    assert res.status_code == 403
