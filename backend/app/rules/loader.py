"""Dataset loader: YAML → compliance_rule / rule_version rows (charter §6).

The YAML files under rules/dataset/ are the reviewable artifact the firm's
professional signs off in PRs. The loader REFUSES entries without a sign-off
outside tests — unsigned rules never reach a calendar.

Usage: python -m app.rules.load  (idempotent: (code, version_no) upserts nothing;
new versions insert; existing versions are immutable and never touched.)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = {"code", "category", "obligation_name", "source_citation", "effective_from"}


class UnsignedRuleError(Exception):
    pass


def load_dataset_files(dataset_dir: Path, allow_test_only: bool = False) -> list[dict[str, Any]]:
    """Parse + validate every YAML file. Raises on unsigned/malformed entries."""
    entries: list[dict[str, Any]] = []
    for path in sorted(dataset_dir.glob("*.yaml")):
        docs = yaml.safe_load(path.read_text()) or []
        if not isinstance(docs, list):
            raise ValueError(f"{path.name}: top level must be a list of rule entries")
        for entry in docs:
            missing = REQUIRED_KEYS - entry.keys()
            if missing:
                raise ValueError(f"{path.name}: {entry.get('code', '?')} missing {sorted(missing)}")
            is_test_only = str(entry["code"]).startswith("TEST-ONLY")
            if not entry.get("signoff"):
                if not (allow_test_only and is_test_only):
                    raise UnsignedRuleError(
                        f"{path.name}: {entry['code']} has no signoff — unsigned rules "
                        "never load outside tests (charter §6)"
                    )
            entries.append(entry)
    return entries
