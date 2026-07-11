"""Dataset pre-flight: `python -m app.rules.check [dataset-dir]`.

Runs in PRs (CI) and on the author's machine BEFORE a dataset merge:
1. Structural validation — every entry parses into the evaluator's RuleData.
2. Dry computation — each rule is exercised against synthetic fixture
   companies (rich attributes AND empty attributes) so broken predicates,
   anchors, offsets, variants, and occurrences fail here, not in production.
3. Sign-off audit — unsigned entries are listed; the production loader will
   refuse them (charter §6), so authors see the gap immediately.

No DB required. Exit code 1 on any structural error.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.rules.evaluator import RuleData, compute_calendar
from app.rules.loader import UnsignedRuleError, load_dataset_files

FY = 2026  # any FY works; the check is structural, not editorial

# A synthetic company that satisfies most anchors/attributes…
RICH_COMPANY = {"agm_date": date(FY, 9, 30)}
RICH_ATTRS = {
    FY: {
        "entity_type": "company",
        "category": "private",
        "is_listed": False,
        "paidup_capital": 50_000_000.0,
        "turnover": 500_000_000.0,
        "net_worth": 100_000_000.0,
        "net_profit": 10_000_000.0,
        "has_tan": True,
        "has_gst_registration": True,
        "has_transfer_pricing": False,
        "has_outstanding_receipts": False,
        "has_msme_dues_over_45d": False,
    },
}
RICH_ATTRS[FY - 1] = RICH_ATTRS[FY]
# …and one with nothing known: every rule must degrade to needs_review, not crash.
BARE_COMPANY: dict[str, Any] = {}
BARE_ATTRS: dict[int, dict[str, Any]] = {FY: {}, FY - 1: {}}


@dataclass
class CheckReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def check_dataset(dataset_dir: Path) -> CheckReport:
    report = CheckReport()
    try:
        entries = load_dataset_files(dataset_dir, allow_test_only=True)
    except (UnsignedRuleError, ValueError) as exc:
        # allow_test_only=True still rejects unsigned NON-test rules; for the
        # pre-flight we want to CHECK them and warn, so retry leniently.
        entries, problem = _lenient_load(dataset_dir)
        if problem:
            report.errors.append(str(exc))
            return report

    for entry in entries:
        code = str(entry.get("code", "?"))
        report.checked += 1
        if not entry.get("signoff"):
            report.warnings.append(
                f"{code}: no signoff — the production loader will REFUSE this entry"
            )
        try:
            rule = RuleData.from_payload(code, 1, _payload(entry))
        except Exception as exc:
            report.errors.append(f"{code}: payload does not parse — {exc}")
            continue
        for label, company, attrs in (
            ("rich fixture", RICH_COMPANY, RICH_ATTRS),
            ("bare fixture", BARE_COMPANY, BARE_ATTRS),
        ):
            try:
                drafts = compute_calendar(company, attrs, FY, [rule])
            except Exception as exc:
                report.errors.append(f"{code}: evaluation crashed on {label} — {exc}")
                continue
            for draft in drafts:
                if draft.computed_due_date is None and not draft.needs_review:
                    report.errors.append(
                        f"{code}: dateless row without needs_review on {label} "
                        "(would emit an unusable calendar row)"
                    )
    return report


def _payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in {"signoff", "effective_from", "effective_to"}}


def _lenient_load(dataset_dir: Path) -> tuple[list[dict[str, Any]], str | None]:
    import yaml

    entries: list[dict[str, Any]] = []
    for path in sorted(dataset_dir.glob("*.yaml")):
        docs = yaml.safe_load(path.read_text()) or []
        if not isinstance(docs, list):
            return [], f"{path.name}: top level must be a list"
        entries.extend(docs)
    return entries, None


def main(argv: list[str]) -> int:
    dataset_dir = Path(argv[1]) if len(argv) > 1 else Path(__file__).parent / "dataset"
    report = check_dataset(dataset_dir)
    print(f"checked {report.checked} rule entr{'y' if report.checked == 1 else 'ies'} "  # noqa: T201
          f"in {dataset_dir}")
    for warning in report.warnings:
        print(f"  WARN  {warning}")  # noqa: T201
    for error in report.errors:
        print(f"  ERROR {error}")  # noqa: T201
    if report.ok:
        print("dataset pre-flight: OK")  # noqa: T201
        return 0
    print("dataset pre-flight: FAILED")  # noqa: T201
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
