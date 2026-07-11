"""Charter §6: unsigned rules never load outside tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.rules.loader import UnsignedRuleError, load_dataset_files

VALID_ENTRY = """
- code: {code}
  category: roc
  obligation_name: Test obligation
  source_citation: TEST-ONLY
  effective_from: 2025-04-01
  {signoff}
"""


def write(tmp_path: Path, code: str, signoff: str = "") -> Path:
    (tmp_path / "rules.yaml").write_text(VALID_ENTRY.format(code=code, signoff=signoff))
    return tmp_path


def test_unsigned_rule_refused(tmp_path: Path) -> None:
    with pytest.raises(UnsignedRuleError):
        load_dataset_files(write(tmp_path, "ROC-REAL"), allow_test_only=False)


def test_unsigned_test_only_rule_refused_in_production_mode(tmp_path: Path) -> None:
    with pytest.raises(UnsignedRuleError):
        load_dataset_files(write(tmp_path, "TEST-ONLY-X"), allow_test_only=False)


def test_unsigned_test_only_rule_allowed_in_test_mode(tmp_path: Path) -> None:
    entries = load_dataset_files(write(tmp_path, "TEST-ONLY-X"), allow_test_only=True)
    assert entries[0]["code"] == "TEST-ONLY-X"


def test_signed_rule_loads(tmp_path: Path) -> None:
    entries = load_dataset_files(
        write(tmp_path, "ROC-REAL", 'signoff: {by: "A. Professional, M.No. 12345", date: 2026-07-01}'),
        allow_test_only=False,
    )
    assert entries[0]["code"] == "ROC-REAL"


def test_missing_required_keys_rejected(tmp_path: Path) -> None:
    (tmp_path / "rules.yaml").write_text("- code: X\n  signoff: {by: someone}\n")
    with pytest.raises(ValueError, match="missing"):
        load_dataset_files(tmp_path, allow_test_only=True)
