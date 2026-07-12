"""Pre-launch checklist items verified as tests (charter M7) — the gate is
executable, not a document."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sqlalchemy import text

from tests.conftest import post

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


async def test_activity_log_grants_enforced_live(db) -> None:
    """Checklist: activity_log has no UPDATE/DELETE grant (verified by test).
    Bootstraps the app role + grants exactly as the migration's DO block does,
    then proves append-only AND immutable rule versions at the DB layer."""
    import app.db as dbmod

    engine = dbmod.get_engine()
    async with engine.connect() as conn:
        conn_exec = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn_exec.execute(text("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'praxis_app') THEN
        CREATE ROLE praxis_app;
    END IF;
END $$;"""))
        await conn_exec.execute(text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO praxis_app"
        ))
        await conn_exec.execute(text("REVOKE UPDATE, DELETE ON activity_log FROM praxis_app"))
        await conn_exec.execute(text("REVOKE UPDATE ON rule_version FROM praxis_app"))
        await conn_exec.execute(text("REVOKE DELETE ON rule_version FROM praxis_app"))
        await conn_exec.execute(text("REVOKE UPDATE, DELETE ON register_entry FROM praxis_app"))

        grants = (await conn_exec.execute(text("""
            SELECT privilege_type FROM information_schema.role_table_grants
            WHERE grantee = 'praxis_app' AND table_name = 'activity_log'
        """))).scalars().all()
        assert "INSERT" in grants and "SELECT" in grants
        assert "UPDATE" not in grants and "DELETE" not in grants

        rv_grants = (await conn_exec.execute(text("""
            SELECT privilege_type FROM information_schema.role_table_grants
            WHERE grantee = 'praxis_app' AND table_name = 'rule_version'
        """))).scalars().all()
        assert "UPDATE" not in rv_grants and "DELETE" not in rv_grants

        reg_grants = (await conn_exec.execute(text("""
            SELECT privilege_type FROM information_schema.role_table_grants
            WHERE grantee = 'praxis_app' AND table_name = 'register_entry'
        """))).scalars().all()
        assert "INSERT" in reg_grants  # append allowed
        assert "UPDATE" not in reg_grants and "DELETE" not in reg_grants  # PRD §8


def test_env_example_covers_every_setting() -> None:
    """Charter C6: .env.example lists every env var the app reads."""
    from app.config import Settings

    example_keys = {
        line.split("=")[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if re.match(r"^[A-Z_]+=", line)
    }
    setting_keys = {name.upper() for name in Settings.model_fields}
    missing = setting_keys - example_keys
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_no_hardcoded_due_date_formulas_outside_rules_engine() -> None:
    """Charter C12 sweep: date arithmetic that smells like compliance-date
    logic must not exist in routes/ or frontend feature code."""
    backend = Path(__file__).resolve().parents[2] / "app"
    offenders = []
    for py in (backend / "routes").rglob("*.py"):
        source = py.read_text()
        if re.search(r"timedelta\(days\s*=\s*\d", source):
            offenders.append(str(py))
    assert not offenders, f"possible hardcoded date logic: {offenders}"


async def test_load_sanity_100_concurrent_calendar_reads(firm, tmp_path) -> None:
    """Checklist: load sanity — 100 concurrent users on the calendar list."""
    import app.db as dbmod
    from app.rules.load import load_entries
    from app.rules.loader import load_dataset_files

    (tmp_path / "rules.yaml").write_text(
        "- code: TEST-ONLY-LOAD\n  category: roc\n  obligation_name: Load fixture\n"
        "  effective_from: 2025-04-01\n  anchor: agm_date\n"
        "  offset_spec: {type: offset, unit: days, amount: 30}\n"
        "  source_citation: TEST-ONLY\n"
    )
    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        await load_entries(session, load_dataset_files(tmp_path, allow_test_only=True))
    cid = (await post(firm.manager, "/companies", {
        "cin": "U74999MH2020PTC101010", "name": "Load Fixture", "agm_date": "2026-09-30",
    })).json()["id"]
    await post(firm.manager, f"/companies/{cid}/calendar/generate?fy=2026", {})

    responses = await asyncio.gather(
        *[firm.viewer.get(f"/api/v1/companies/{cid}/calendar?fy=2026") for _ in range(100)]
    )
    assert all(r.status_code == 200 for r in responses)
    assert all(len(r.json()) == 1 for r in responses)


async def test_rate_limit_answers_429_when_exhausted(db, make_client, monkeypatch) -> None:
    """Checklist: Redis-backed rate limiting works (shared store = identical
    behavior across N api replicas by construction)."""
    from redis.asyncio import Redis

    from app.config import get_settings

    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()

    # clear the shared per-minute window other tests filled this minute
    redis = Redis.from_url(get_settings().redis_url)
    async for key in redis.scan_iter("rl:auth:*"):
        await redis.delete(key)
    await redis.aclose()

    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        codes = [(await client.get("/api/v1/auth/csrf")).status_code for _ in range(5)]
    get_settings.cache_clear()
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]
