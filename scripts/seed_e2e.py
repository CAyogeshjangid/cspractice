"""E2E / dogfood seeding (charter C6: ops script, never imported by app).

Prepares a database for the FULL-FLOW browser E2E and local dogfooding:
1. Loads a TEST-ONLY ruleset (charter §6: clearly marked, never real content).
2. Syncs the template registry and stamps every template as a TEST reviewer —
   stamps in this environment assert nothing professionally.
3. Writes a small sample portfolio .xlsx to frontend/e2e/fixtures/.

Run:  DATABASE_URL=... REDIS_URL=... JWT_SECRET=... CSRF_SECRET=... \
      CORS_ORIGINS=... python scripts/seed_e2e.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

RULESET = """
- code: TEST-ONLY-E2E-AGM30
  category: roc
  obligation_name: "[TEST] File within 30 days of AGM"
  form_number: TST-1
  effective_from: 2025-04-01
  anchor: agm_date
  offset_spec: {type: offset, unit: days, amount: 30}
  source_citation: TEST-ONLY — dogfood fixture, not a real obligation

- code: TEST-ONLY-E2E-FIXED
  category: income_tax
  obligation_name: "[TEST] Fixed-date obligation"
  effective_from: 2025-04-01
  anchor: fixed_date
  offset_spec: {type: fixed, month: 10, day: 31, year_ref: fy_end_year}
  source_citation: TEST-ONLY — dogfood fixture

- code: TEST-ONLY-E2E-UNKNOWN
  category: gst
  obligation_name: "[TEST] Turnover-gated obligation (exercises review queue)"
  effective_from: 2025-04-01
  applicability:
    all:
      - {attr: turnover, op: gte, value: 20000000}
  anchor: fixed_date
  offset_spec: {type: fixed, month: 12, day: 31, year_ref: fy_end_year}
  source_citation: TEST-ONLY — dogfood fixture
"""

PORTFOLIO = [
    ("U11111MH2019PTC111111", "Alpha Textiles Pvt Ltd", "2026-09-30", 5000000),
    ("U22222DL2020PTC222222", "Beta Software Pvt Ltd", "2026-09-25", 12000000),
    ("U33333KA2021PTC333333", "Gamma Foods Pvt Ltd", "", 800000),  # no AGM → review row
]


DIRECTORS = [
    ("Asha Mehta", "00000101", "Managing Director"),
    ("Ravi Kulkarni", "00000102", "Director"),
]


def build_portfolio_xlsx() -> Path:
    from openpyxl import Workbook

    fixtures = ROOT / "frontend" / "e2e" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    out = fixtures / "portfolio.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["cin", "name", "agm_date", "paidup_capital"])
    for cin, name, agm, capital in PORTFOLIO:
        ws.append([cin, name, agm or None, capital])
    wb.save(out)
    return out


def build_directors_xlsx() -> Path:
    """Fixture for the per-master import UI (M15/M16) — headers must match
    app.services.imports.MASTER_SPECS['directors']."""
    from openpyxl import Workbook

    fixtures = ROOT / "frontend" / "e2e" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    out = fixtures / "directors.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["name", "din", "din_status", "din_allocation_date", "designation",
               "appointment_date", "cessation_date"])
    for name, din, designation in DIRECTORS:
        ws.append([name, din, None, None, designation, None, None])
    wb.save(out)
    return out


async def seed_db() -> None:
    from app.db import get_engine, get_session
    from app.models import DocTemplate
    from app.rules.load import load_entries
    from app.rules.loader import load_dataset_files
    from app.services.documents import sync_templates
    from sqlalchemy import select, update

    get_engine()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "rules.yaml").write_text(RULESET)
        entries = load_dataset_files(Path(tmp), allow_test_only=True)
        async for session in get_session():
            summary = await load_entries(session, entries)
            print(f"rules: {summary}")  # noqa: T201

            await sync_templates(session)
            count = (
                await session.execute(
                    update(DocTemplate)
                    .where(DocTemplate.validated_at.is_(None))
                    .values(
                        validated_by="TEST-ONLY Reviewer (E2E)",
                        validated_membership_no="TEST",
                        validated_at=datetime.now(timezone.utc),
                    )
                )
            ).rowcount
            await session.commit()
            total = len((await session.execute(select(DocTemplate))).scalars().all())
            print(f"templates: {total} synced, {count} test-stamped")  # noqa: T201


if __name__ == "__main__":
    path = build_portfolio_xlsx()
    print(f"portfolio fixture: {path}")  # noqa: T201
    path = build_directors_xlsx()
    print(f"directors fixture: {path}")  # noqa: T201
    asyncio.run(seed_db())
    print("e2e seed complete")  # noqa: T201
