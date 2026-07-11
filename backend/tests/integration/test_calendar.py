"""M4 acceptance: golden dates from a TEST-ONLY ruleset, version changes flag
(never rewrite), FK integrity, RBAC flows, filed-with-SRN, extensions."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.conftest import post

FY = 2026
COMPANY = {
    "cin": "U74999MH2020PTC999999",
    "name": "Golden Fixture Pvt Ltd",
    "agm_date": "2026-09-30",
    "paidup_capital": 60000000,
}

RULESET_V1 = """
- code: TEST-ONLY-AGM30
  category: roc
  obligation_name: File within 30 days of AGM
  form_number: TST-1
  effective_from: 2025-04-01
  anchor: agm_date
  offset_spec: {type: offset, unit: days, amount: 30}
  source_citation: TEST-ONLY citation A

- code: TEST-ONLY-TURNOVER
  category: gst
  obligation_name: Applies only above a turnover threshold
  effective_from: 2025-04-01
  applicability:
    all:
      - {attr: turnover, op: gte, value: 1000000000}
  anchor: fixed_date
  offset_spec: {type: fixed, month: 12, day: 31, year_ref: fy_end_year}
  source_citation: TEST-ONLY citation B

- code: TEST-ONLY-NEVER
  category: roc
  obligation_name: Never applies to the fixture
  effective_from: 2025-04-01
  applicability:
    all:
      - {attr: paidup_capital, op: gte, value: 1000000000000}
  anchor: fy_end
  offset_spec: {type: offset, unit: days, amount: 1}
  source_citation: TEST-ONLY citation C

- code: TEST-ONLY-KYC
  category: roc
  obligation_name: Per-director KYC
  effective_from: 2025-04-01
  subject: director
  anchor: fixed_date
  offset_spec: {type: fixed, month: 9, day: 30, year_ref: fy_end_year}
  source_citation: TEST-ONLY citation D

- code: TEST-ONLY-HALF
  category: income_tax
  obligation_name: Half-yearly obligation
  effective_from: 2025-04-01
  anchor: fixed_date
  occurrences:
    - {label: H1, offset_spec: {type: fixed, month: 10, day: 31, year_ref: fy_start_year}}
    - {label: H2, offset_spec: {type: fixed, month: 4, day: 30, year_ref: fy_end_year}}
  source_citation: TEST-ONLY citation E
"""

# v2 changes ONLY the AGM offset: 30 → 45 days
RULESET_V2 = RULESET_V1.replace(
    "offset_spec: {type: offset, unit: days, amount: 30}",
    "offset_spec: {type: offset, unit: days, amount: 45}",
)


async def load_rules(tmp_path: Path, yaml_text: str) -> dict:
    import app.db as dbmod
    from app.rules.load import load_entries
    from app.rules.loader import load_dataset_files

    (tmp_path / "rules.yaml").write_text(yaml_text)
    entries = load_dataset_files(tmp_path, allow_test_only=True)
    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        return await load_entries(session, entries)


async def setup_calendar(firm, tmp_path, ruleset: str = RULESET_V1) -> str:
    """Create fixture company + two directors, load rules, generate. → company_id"""
    await load_rules(tmp_path, ruleset)
    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    await post(firm.manager, f"/companies/{cid}/directors", {
        "name": "Dated DIN", "din": "01111111", "din_allocation_date": "2015-01-01",
    })
    await post(firm.manager, f"/companies/{cid}/directors", {
        "name": "Undated DIN", "din": "02222222",
    })
    await post(firm.manager, f"/companies/{cid}/directors", {"name": "No DIN"})
    res = await post(firm.manager, f"/companies/{cid}/calendar/generate?fy={FY}", {})
    assert res.status_code == 200, res.text
    return cid


async def rows_by_code(client, cid: str) -> dict:
    res = await client.get(f"/api/v1/companies/{cid}/calendar?fy={FY}")
    assert res.status_code == 200, res.text
    return {f"{r['rule_code']}:{r['occurrence_label']}": r for r in res.json()}


async def test_golden_dates_and_trace(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)
    rows = await rows_by_code(firm.viewer, cid)

    agm = rows["TEST-ONLY-AGM30:"]
    assert agm["computed_due_date"] == "2026-10-30"  # AGM 30 Sep + 30d
    assert agm["effective_due_date"] == "2026-10-30"
    assert (agm["rule_version"], agm["citation"]) == (1, "TEST-ONLY citation A")
    assert agm["needs_review"] is False

    # UNKNOWN turnover → emitted flagged, never dropped (G1)
    turnover = rows["TEST-ONLY-TURNOVER:"]
    assert turnover["computed_due_date"] == "2026-12-31"
    assert turnover["needs_review"] is True
    assert turnover["needs_review_reason"] == "applicability_unknown"

    # FALSE applicability → no row at all
    assert not any(k.startswith("TEST-ONLY-NEVER") for k in rows)

    # occurrences → two labeled rows (G7)
    assert rows["TEST-ONLY-HALF:H1"]["computed_due_date"] == "2025-10-31"
    assert rows["TEST-ONLY-HALF:H2"]["computed_due_date"] == "2026-04-30"

    # per-director expansion (G6): dated DIN clean, undated flagged, no-DIN skipped
    # (fetch the raw list — the by-code dict collapses same-code rows)
    raw = (await firm.viewer.get(f"/api/v1/companies/{cid}/calendar?fy={FY}")).json()
    kyc = [r for r in raw if r["rule_code"] == "TEST-ONLY-KYC"]
    assert len(kyc) == 2
    assert all(r["subject_type"] == "director" and r["subject_id"] for r in kyc)
    flags = sorted(r["needs_review"] for r in kyc)
    assert flags == [False, True]


async def test_regenerate_is_idempotent_and_preserves_user_state(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)
    rows = await rows_by_code(firm.manager, cid)
    row_id = rows["TEST-ONLY-AGM30:"]["id"]

    res = await post(firm.manager, f"/calendar-rows/{row_id}",
                     {"remarks": "working on it", "status": "in_progress"}, method="PATCH")
    assert res.status_code == 200

    regen = (await post(firm.manager, f"/companies/{cid}/calendar/generate?fy={FY}", {})).json()
    assert regen["created"] == 0 and regen["revised"] == 0

    rows = await rows_by_code(firm.manager, cid)
    assert rows["TEST-ONLY-AGM30:"]["remarks"] == "working on it"
    assert rows["TEST-ONLY-AGM30:"]["status"] == "in_progress"


async def test_rule_version_change_flags_never_rewrites(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)

    # loading v2 (offset 30→45) creates version 2 and flags the pinned row
    summary = await load_rules(tmp_path, RULESET_V2)
    assert summary["versions_added"] == 1

    rows = await rows_by_code(firm.manager, cid)
    agm = rows["TEST-ONLY-AGM30:"]
    assert agm["computed_due_date"] == "2026-10-30"  # date NOT silently rewritten
    assert agm["needs_review"] is True
    assert agm["needs_review_reason"] == "rule_revised"

    # explicit regenerate applies the new date, still flagged, audit-trailed
    await post(firm.manager, f"/companies/{cid}/calendar/generate?fy={FY}", {})
    agm = (await rows_by_code(firm.manager, cid))["TEST-ONLY-AGM30:"]
    assert agm["computed_due_date"] == "2026-11-14"  # AGM + 45d
    assert agm["rule_version"] == 2
    assert agm["needs_review"] is True

    # reviewer acknowledges → flag clears
    await post(firm.manager, f"/calendar-rows/{agm['id']}",
               {"acknowledge_review": True}, method="PATCH")
    agm = (await rows_by_code(firm.manager, cid))["TEST-ONLY-AGM30:"]
    assert agm["needs_review"] is False

    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ActivityLog

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        actions = (await session.execute(select(ActivityLog.action))).scalars().all()
    assert "rule_revised" in actions and "date_revised" in actions


async def test_filed_requires_srn_or_offline_ack(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)
    row_id = (await rows_by_code(firm.manager, cid))["TEST-ONLY-AGM30:"]["id"]

    res = await post(firm.manager, f"/calendar-rows/{row_id}", {"status": "filed"},
                     method="PATCH")
    assert res.status_code == 422

    res = await post(firm.manager, f"/calendar-rows/{row_id}",
                     {"status": "filed", "srn": "T12345678"}, method="PATCH")
    assert res.status_code == 200
    assert (await rows_by_code(firm.viewer, cid))["TEST-ONLY-AGM30:"]["srn"] == "T12345678"


async def test_override_is_manager_plus_and_needs_reason(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)
    rows = await rows_by_code(firm.manager, cid)
    row_id = rows["TEST-ONLY-AGM30:"]["id"]

    # assign to executive so their block is the override rule, not assignment
    await post(firm.manager, f"/calendar-rows/{row_id}",
               {"assignee_user_id": None}, method="PATCH")
    res = await post(firm.executive, f"/calendar-rows/{row_id}",
                     {"override_date": "2026-12-01", "override_reason": "x"}, method="PATCH")
    assert res.status_code == 403  # executive: not even on assigned rows

    res = await post(firm.manager, f"/calendar-rows/{row_id}",
                     {"override_date": "2026-12-01"}, method="PATCH")
    assert res.status_code == 422  # reason required

    res = await post(firm.manager, f"/calendar-rows/{row_id}",
                     {"override_date": "2026-12-01", "override_reason": "client extension"},
                     method="PATCH")
    assert res.status_code == 200
    row = (await rows_by_code(firm.viewer, cid))["TEST-ONLY-AGM30:"]
    assert row["computed_due_date"] == "2026-10-30"  # computed survives (PRD §4.5)
    assert row["effective_due_date"] == "2026-12-01"


async def test_executive_edits_assigned_rows_only(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)
    rows = await rows_by_code(firm.manager, cid)
    row_id = rows["TEST-ONLY-AGM30:"]["id"]

    res = await post(firm.executive, f"/calendar-rows/{row_id}",
                     {"remarks": "not mine"}, method="PATCH")
    assert res.status_code == 403

    exec_user_id = None
    import app.db as dbmod
    from sqlalchemy import select

    from app.models import User

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        exec_user_id = (
            await session.execute(select(User.id).where(User.email == "executive@example.com"))
        ).scalar_one()
    await post(firm.manager, f"/calendar-rows/{row_id}",
               {"assignee_user_id": str(exec_user_id)}, method="PATCH")

    res = await post(firm.executive, f"/calendar-rows/{row_id}",
                     {"remarks": "mine now"}, method="PATCH")
    assert res.status_code == 200


async def test_extension_recorded_beside_computed_date(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)

    import app.db as dbmod
    from sqlalchemy import select

    from app.models import ComplianceRule, RuleExtension

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        rule_id = (
            await session.execute(
                select(ComplianceRule.id).where(ComplianceRule.code == "TEST-ONLY-AGM30")
            )
        ).scalar_one()
        session.add(RuleExtension(
            rule_id=rule_id, circular_ref="TEST-CIRC 9/2026", circular_date=date(2026, 8, 1),
            applies_fy=FY, extended_due_date=date(2026, 12, 31), signed_off_by="TEST-ONLY",
        ))
        await session.commit()

    await post(firm.manager, f"/companies/{cid}/calendar/generate?fy={FY}", {})
    row = (await rows_by_code(firm.viewer, cid))["TEST-ONLY-AGM30:"]
    assert row["computed_due_date"] == "2026-10-30"      # never overwritten
    assert row["extension_date"] == "2026-12-31"
    assert row["extension_ref"] == "TEST-CIRC 9/2026"
    assert row["effective_due_date"] == "2026-12-31"


async def test_fy_attributes_rbac_and_effect(firm, tmp_path) -> None:
    cid = await setup_calendar(firm, tmp_path)

    res = await post(firm.executive, f"/companies/{cid}/fy-attributes/{FY}",
                     {"turnover": 2000000000}, method="PUT")
    assert res.status_code == 403  # Manager+ only (Amendment A1)

    res = await post(firm.manager, f"/companies/{cid}/fy-attributes/{FY}",
                     {"turnover": 2000000000}, method="PUT")
    assert res.status_code == 200
    got = (await firm.viewer.get(f"/api/v1/companies/{cid}/fy-attributes/{FY}")).json()
    assert got["turnover"] == 2000000000.0


async def test_calendar_row_requires_rule_version_fk(firm, tmp_path) -> None:
    """M4 acceptance: a calendar row can never exist without a rule_version FK."""
    import uuid as uuid_mod

    import app.db as dbmod
    from sqlalchemy.exc import IntegrityError

    from app.models import CalendarRow, Firm
    from sqlalchemy import select

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        firm_id = (await session.execute(select(Firm.id))).scalars().first()
        session.add(CalendarRow(
            firm_id=firm_id, company_id=uuid_mod.uuid4(), fy=FY, rule_version_id=None,
        ))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_calendar_rbac_and_isolation(firm, tmp_path, make_client) -> None:
    cid = await setup_calendar(firm, tmp_path)
    res = await post(firm.viewer, f"/companies/{cid}/calendar/generate?fy={FY}", {})
    assert res.status_code == 403

    from tests.conftest import register_firm

    rival = make_client()
    await register_firm(rival, "rival-cal@example.com", "Rival")
    assert (await rival.get(f"/api/v1/companies/{cid}/calendar?fy={FY}")).status_code == 404

    export = await firm.viewer.get(f"/api/v1/companies/{cid}/calendar/export?fy={FY}")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/vnd.openxmlformats")