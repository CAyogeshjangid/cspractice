"""Golden-file tests for compute_calendar (charter M4 acceptance).

All rules here are TEST-ONLY fixtures (charter §6) — offsets are chosen to
exercise engine mechanics, not to assert real statutory dates.
"""
from __future__ import annotations

from datetime import date

from app.rules.evaluator import CalendarRowDraft, Extension, RuleData, compute_calendar

FY = 2026  # FY 2025-26: 1 Apr 2025 – 31 Mar 2026


def rule(code: str, **overrides) -> RuleData:
    base = dict(
        code=code,
        version_no=1,
        category="roc",
        obligation_name=f"Test obligation {code}",
        form_number=None,
        citation="TEST-ONLY",
        applicability=None,
        anchor="agm_date",
        offset_spec={"type": "offset", "unit": "days", "amount": 30},
    )
    base.update(overrides)
    return RuleData(**base)


COMPANY = {"agm_date": date(2026, 9, 30)}
ATTRS: dict[int, dict] = {FY: {"paidup_capital": 60_000_000}}


def by_code(drafts: list[CalendarRowDraft]) -> dict[str, CalendarRowDraft]:
    return {f"{d.rule_code}:{d.occurrence_label}": d for d in drafts}


def test_agm_anchored_offset() -> None:
    drafts = compute_calendar(COMPANY, ATTRS, FY, [rule("TEST-ONLY-A")])
    assert drafts[0].computed_due_date == date(2026, 10, 30)  # AGM + 30d
    assert not drafts[0].needs_review
    # traceability: every draft carries code, version, citation (charter §6)
    assert (drafts[0].rule_code, drafts[0].rule_version, drafts[0].citation) == (
        "TEST-ONLY-A", 1, "TEST-ONLY",
    )


def test_missing_anchor_emits_dateless_needs_review_never_guesses() -> None:
    drafts = compute_calendar({}, ATTRS, FY, [rule("TEST-ONLY-A")])
    d = drafts[0]
    assert d.computed_due_date is None
    assert d.needs_review and d.needs_review_reason == "missing_anchor"


def test_anchor_fallback_list() -> None:
    """G3: [agm_date, fy_end+6m] — falls back when AGM is unset."""
    r = rule("TEST-ONLY-A", anchor=["agm_date", {"fy_end": {"plus_months": 6}}])
    drafts = compute_calendar({}, ATTRS, FY, [r])
    # fy_end 31 Mar 2026 + 6 months (clamped) = 30 Sep 2026, + 30d = 30 Oct 2026
    assert drafts[0].computed_due_date == date(2026, 10, 30)
    assert not drafts[0].needs_review


def test_unknown_applicability_emits_flagged_row_not_silence() -> None:
    """G1: the load-bearing behavior — UNKNOWN never silently drops a row."""
    r = rule(
        "TEST-ONLY-XBRL",
        applicability={"attr": "turnover", "op": "gte", "value": 1_000_000_000},
    )
    drafts = compute_calendar(COMPANY, ATTRS, FY, [r])  # turnover not in ATTRS
    assert len(drafts) == 1
    assert drafts[0].needs_review and drafts[0].needs_review_reason == "applicability_unknown"


def test_false_applicability_emits_nothing() -> None:
    r = rule(
        "TEST-ONLY-BIG",
        applicability={"attr": "paidup_capital", "op": "gte", "value": 10**12},
    )
    assert compute_calendar(COMPANY, ATTRS, FY, [r]) == []


def test_supersession_true_suppresses_general_row() -> None:
    """G2: MGT-7A-style — specific TRUE removes the general row."""
    general = rule("TEST-ONLY-GEN")
    specific = rule(
        "TEST-ONLY-SPEC",
        applicability={"attr": "paidup_capital", "op": "lte", "value": 100_000_000},
        supersedes=["TEST-ONLY-GEN"],
    )
    drafts = compute_calendar(COMPANY, ATTRS, FY, [general, specific])
    codes = {d.rule_code for d in drafts}
    assert codes == {"TEST-ONLY-SPEC"}


def test_supersession_unknown_keeps_both_flagged() -> None:
    general = rule("TEST-ONLY-GEN")
    specific = rule(
        "TEST-ONLY-SPEC",
        applicability={"attr": "turnover", "op": "lte", "value": 100},  # unknown
        supersedes=["TEST-ONLY-GEN"],
    )
    drafts = by_code(compute_calendar(COMPANY, ATTRS, FY, [general, specific]))
    assert set(d.split(":")[0] for d in drafts) == {"TEST-ONLY-GEN", "TEST-ONLY-SPEC"}
    assert all(d.needs_review for d in drafts.values())


def test_occurrences_emit_multiple_rows() -> None:
    """G7: MSME-1-style half-yearly — two rows, labeled, one per occurrence."""
    r = rule(
        "TEST-ONLY-HALF",
        anchor="fixed_date",
        offset_spec=None,
        occurrences=[
            {"label": "H1", "offset_spec": {"type": "fixed", "month": 10, "day": 31,
                                            "year_ref": "fy_start_year"}},
            {"label": "H2", "offset_spec": {"type": "fixed", "month": 4, "day": 30,
                                            "year_ref": "fy_end_year"}},
        ],
    )
    drafts = by_code(compute_calendar(COMPANY, ATTRS, FY, [r]))
    assert drafts["TEST-ONLY-HALF:H1"].computed_due_date == date(2025, 10, 31)
    assert drafts["TEST-ONLY-HALF:H2"].computed_due_date == date(2026, 4, 30)


def test_variant_overrides_offset_when_true() -> None:
    """ITR-6-style: TP cases get a later fixed date."""
    r = rule(
        "TEST-ONLY-ITR",
        anchor="fixed_date",
        offset_spec={"type": "fixed", "month": 10, "day": 31, "year_ref": "fy_end_year"},
        variants=[{
            "when": {"attr": "has_transfer_pricing", "op": "eq", "value": True},
            "offset_spec": {"type": "fixed", "month": 11, "day": 30, "year_ref": "fy_end_year"},
        }],
    )
    attrs = {FY: {"has_transfer_pricing": True}}
    drafts = compute_calendar(COMPANY, attrs, FY, [r])
    assert drafts[0].computed_due_date == date(2026, 11, 30)


def test_variant_unknown_keeps_base_date_but_flags() -> None:
    r = rule(
        "TEST-ONLY-ITR",
        anchor="fixed_date",
        offset_spec={"type": "fixed", "month": 10, "day": 31, "year_ref": "fy_end_year"},
        variants=[{
            "when": {"attr": "has_transfer_pricing", "op": "eq", "value": True},
            "offset_spec": {"type": "fixed", "month": 11, "day": 30, "year_ref": "fy_end_year"},
        }],
    )
    drafts = compute_calendar(COMPANY, ATTRS, FY, [r])  # TP flag unknown
    d = drafts[0]
    assert d.computed_due_date == date(2026, 10, 31)  # base date kept
    assert d.needs_review and d.needs_review_reason == "applicability_unknown"


def test_extension_recorded_beside_computed_date_never_over_it() -> None:
    ext = Extension(
        rule_code="TEST-ONLY-A",
        circular_ref="TEST-CIRC-1/2026",
        applies_fy=FY,
        applies_predicate=None,
        extended_due_date=date(2026, 12, 31),
    )
    drafts = compute_calendar(COMPANY, ATTRS, FY, [rule("TEST-ONLY-A")], [ext])
    d = drafts[0]
    assert d.computed_due_date == date(2026, 10, 30)  # original preserved (PRD §4.5)
    assert d.extension_date == date(2026, 12, 31)
    assert d.extension_ref == "TEST-CIRC-1/2026"


def test_phase3_rules_are_skipped_explicitly() -> None:
    """G4: BEN-2-style event-anchored rules carry phase: 3 and never emit."""
    r = rule("TEST-ONLY-EVENT", phase=3)
    assert compute_calendar(COMPANY, ATTRS, FY, [r]) == []
