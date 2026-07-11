"""compute_calendar — the core evaluator (charter §6 + Amendment A1).

Pure function over plain data: no DB, no I/O. The service layer feeds it
rule-version payloads and company/FY attributes and persists the drafts.

Guarantees:
- UNKNOWN applicability → row emitted with needs_review=applicability_unknown,
  never silently dropped (G1).
- Unresolvable anchor → row emitted dateless with needs_review=missing_anchor,
  never guessed (charter §6.3).
- Extensions recorded beside the computed date, never over it (PRD §4.5).
- supersedes: specific rule TRUE suppresses the general row; UNKNOWN keeps
  both, flagged (G2).
- phase != 1 rules are skipped as an EXPLICIT dataset decision (G4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.rules.dates import apply_offset, resolve_anchor
from app.rules.predicates import AttributeBag, Tri, evaluate


@dataclass
class RuleData:
    """A rule at one immutable version, as consumed by the evaluator."""

    code: str
    version_no: int
    category: str
    obligation_name: str
    form_number: str | None
    citation: str
    applicability: dict[str, Any] | None
    anchor: Any  # name | spec | ordered fallback list
    offset_spec: dict[str, Any] | None
    variants: list[dict[str, Any]] = field(default_factory=list)
    occurrences: list[dict[str, Any]] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    subject: str = "company"  # company | director (G6)
    phase: int = 1

    @classmethod
    def from_payload(cls, code: str, version_no: int, payload: dict[str, Any]) -> "RuleData":
        return cls(
            code=code,
            version_no=version_no,
            category=payload["category"],
            obligation_name=payload["obligation_name"],
            form_number=payload.get("form_number"),
            citation=payload["source_citation"],
            applicability=payload.get("applicability"),
            anchor=payload.get("anchor"),
            offset_spec=payload.get("offset_spec"),
            variants=payload.get("variants", []),
            occurrences=payload.get("occurrences", []),
            supersedes=payload.get("supersedes", []),
            subject=payload.get("subject", "company"),
            phase=int(payload.get("phase", 1)),
        )


@dataclass
class Extension:
    rule_code: str
    circular_ref: str
    applies_fy: int
    applies_predicate: dict[str, Any] | None
    extended_due_date: date


@dataclass
class CalendarRowDraft:
    rule_code: str
    rule_version: int
    citation: str
    obligation_name: str
    form_number: str | None
    category: str
    fy: int
    occurrence_label: str = ""
    subject_type: str = "company"
    computed_due_date: date | None = None
    extension_date: date | None = None
    extension_ref: str | None = None
    needs_review: bool = False
    needs_review_reason: str | None = None  # missing_anchor | applicability_unknown


def compute_calendar(
    company: dict[str, Any],
    attrs: AttributeBag,
    fy: int,
    rules: list[RuleData],
    extensions: list[Extension] | None = None,
) -> list[CalendarRowDraft]:
    drafts: dict[str, list[CalendarRowDraft]] = {}
    applicability_result: dict[str, Tri] = {}

    for rule in rules:
        if rule.phase != 1:
            continue  # explicit dataset exclusion (G4), not a silent gap

        result = evaluate(rule.applicability, attrs, fy)
        applicability_result[rule.code] = result
        if result is Tri.FALSE:
            continue

        rows = _emit_rows(rule, company, attrs, fy)
        if result is Tri.UNKNOWN:
            for row in rows:
                row.needs_review = True
                row.needs_review_reason = row.needs_review_reason or "applicability_unknown"
        drafts[rule.code] = rows

    _apply_supersession(drafts, applicability_result, rules)
    _apply_extensions(drafts, attrs, fy, extensions or [])

    return [row for rows in drafts.values() for row in rows]


def _emit_rows(
    rule: RuleData, company: dict[str, Any], attrs: AttributeBag, fy: int
) -> list[CalendarRowDraft]:
    offset_specs: list[tuple[str, dict[str, Any] | None]]
    if rule.occurrences:
        offset_specs = [(o["label"], o["offset_spec"]) for o in rule.occurrences]  # G7
    else:
        offset_specs = [("", rule.offset_spec)]

    # Variants: first TRUE variant overrides the offset; any UNKNOWN variant
    # keeps the base date but flags the row (e.g. ITR-6 TP extension unknown).
    variant_unknown = False
    for variant in rule.variants:
        v_result = evaluate(variant.get("when"), attrs, fy)
        if v_result is Tri.TRUE:
            offset_specs = [("", variant["offset_spec"])]
            break
        if v_result is Tri.UNKNOWN:
            variant_unknown = True

    rows = []
    for label, offset_spec in offset_specs:
        row = CalendarRowDraft(
            rule_code=rule.code,
            rule_version=rule.version_no,
            citation=rule.citation,
            obligation_name=rule.obligation_name,
            form_number=rule.form_number,
            category=rule.category,
            fy=fy,
            occurrence_label=label,
            subject_type=rule.subject,
        )
        anchor = resolve_anchor(rule.anchor, company, fy) if rule.anchor else None
        due = apply_offset(offset_spec, anchor, fy) if offset_spec else None
        if due is None:
            row.needs_review = True
            row.needs_review_reason = "missing_anchor"
        else:
            row.computed_due_date = due
            if variant_unknown:
                row.needs_review = True
                row.needs_review_reason = "applicability_unknown"
        rows.append(row)
    return rows


def _apply_supersession(
    drafts: dict[str, list[CalendarRowDraft]],
    results: dict[str, Tri],
    rules: list[RuleData],
) -> None:
    for rule in rules:
        if rule.code not in drafts:
            continue
        for superseded_code in rule.supersedes:
            if superseded_code not in drafts:
                continue
            if results[rule.code] is Tri.TRUE:
                del drafts[superseded_code]  # specific rule definitely applies (G2)
            else:  # UNKNOWN — keep both, flagged, let the professional decide
                for row in drafts[superseded_code]:
                    row.needs_review = True
                    row.needs_review_reason = row.needs_review_reason or "applicability_unknown"


def _apply_extensions(
    drafts: dict[str, list[CalendarRowDraft]],
    attrs: AttributeBag,
    fy: int,
    extensions: list[Extension],
) -> None:
    for ext in extensions:
        if ext.applies_fy != fy or ext.rule_code not in drafts:
            continue
        applies = evaluate(ext.applies_predicate, attrs, fy)
        if applies is Tri.FALSE:
            continue
        for row in drafts[ext.rule_code]:
            # recorded BESIDE the computed date, never over it (PRD §4.5)
            row.extension_date = ext.extended_due_date
            row.extension_ref = ext.circular_ref
            if applies is Tri.UNKNOWN:
                row.needs_review = True
                row.needs_review_reason = row.needs_review_reason or "applicability_unknown"
