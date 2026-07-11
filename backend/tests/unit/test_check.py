"""Dataset pre-flight checker (editorial pipeline tooling)."""
from __future__ import annotations

from pathlib import Path

from app.rules.check import check_dataset

GOOD = """
- code: ROC-DRAFT-1
  category: roc
  obligation_name: Well formed rule
  effective_from: 2025-04-01
  anchor: [agm_date, {fy_end: {plus_months: 6}}]
  offset_spec: {type: offset, unit: days, amount: 30}
  source_citation: Draft citation
  signoff: {by: "A Professional", date: 2026-07-01}
"""

UNSIGNED = GOOD.replace('  signoff: {by: "A Professional", date: 2026-07-01}\n', "")

BROKEN_OFFSET = """
- code: ROC-BROKEN
  category: roc
  obligation_name: Broken offset unit
  effective_from: 2025-04-01
  anchor: fy_end
  offset_spec: {type: offset, unit: fortnights, amount: 2}
  source_citation: Draft
  signoff: {by: "A Professional"}
"""

BROKEN_PREDICATE = """
- code: ROC-BADPRED
  category: roc
  obligation_name: Malformed predicate node
  effective_from: 2025-04-01
  applicability: {sometimes: []}
  anchor: fy_end
  offset_spec: {type: offset, unit: days, amount: 1}
  source_citation: Draft
  signoff: {by: "A Professional"}
"""


def write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "rules.yaml").write_text(text)
    return tmp_path


def test_good_dataset_passes(tmp_path: Path) -> None:
    report = check_dataset(write(tmp_path, GOOD))
    assert report.ok and report.checked == 1 and not report.warnings


def test_unsigned_entry_warns_but_structurally_checks(tmp_path: Path) -> None:
    report = check_dataset(write(tmp_path, UNSIGNED))
    assert report.ok  # structure fine
    assert any("REFUSE" in w for w in report.warnings)


def test_broken_offset_reported_with_rule_code(tmp_path: Path) -> None:
    report = check_dataset(write(tmp_path, BROKEN_OFFSET))
    assert not report.ok
    assert any("ROC-BROKEN" in e and "fortnights" in e for e in report.errors)


def test_malformed_predicate_reported(tmp_path: Path) -> None:
    report = check_dataset(write(tmp_path, BROKEN_PREDICATE))
    assert not report.ok
    assert any("ROC-BADPRED" in e for e in report.errors)


def test_shipped_dataset_dir_passes() -> None:
    """The committed dataset (currently empty) must always pre-flight clean —
    this is the CI gate for every future dataset PR."""
    dataset = Path(__file__).resolve().parents[2] / "app" / "rules" / "dataset"
    report = check_dataset(dataset)
    assert report.ok
