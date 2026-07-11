"""Idempotent dataset loader: YAML entries → compliance_rule/rule_version rows.

`python -m app.rules.load` (charter §6). Re-running with an unchanged dataset
inserts nothing. A changed entry inserts a NEW immutable version (never edits
the old one) and flags every calendar row still referencing the older versions
as needs_review/rule_revised — dates are never silently rewritten (PRD §7).
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.models import CalendarRow, ComplianceRule, NeedsReviewReason, RuleVersion
from app.repositories import rules as repo
from app.rules.loader import load_dataset_files

DATASET_DIR = Path(__file__).parent / "dataset"

# entry keys that are loader metadata, not evaluator payload
META_KEYS = {"signoff", "effective_from", "effective_to"}


def entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in META_KEYS}


async def load_entries(
    session: AsyncSession,
    entries: list[dict[str, Any]],
) -> dict[str, int]:
    created_rules = new_versions = unchanged = 0
    for entry in entries:
        rule = await repo.get_rule_by_code(session, entry["code"])
        if rule is None:
            rule = ComplianceRule(
                code=entry["code"],
                category=entry["category"],
                obligation_name=entry["obligation_name"],
                form_number=entry.get("form_number"),
            )
            session.add(rule)
            await session.flush()
            created_rules += 1

        payload = entry_payload(entry)
        latest = await repo.latest_version(session, rule.id)
        if latest is not None and latest.payload == payload:
            unchanged += 1
            continue

        signoff = entry.get("signoff") or {}
        effective_from = entry["effective_from"]
        if isinstance(effective_from, str):
            effective_from = date.fromisoformat(effective_from)
        version = await repo.insert_version(
            session,
            rule,
            version_no=(latest.version_no + 1) if latest else 1,
            effective_from=effective_from,
            payload=payload,
            signed_off_by=signoff.get("by", "TEST-ONLY"),
            signoff_note=signoff.get("note"),
            source_document_ref=entry["source_citation"],
        )
        new_versions += 1
        if latest is not None:
            await _flag_stale_rows(session, rule.id, version)
    await session.commit()
    return {"rules_created": created_rules, "versions_added": new_versions, "unchanged": unchanged}


async def _flag_stale_rows(
    session: AsyncSession, rule_id: uuid.UUID, new_version: RuleVersion
) -> None:
    """Rows pinned to older versions of this rule: flag, never rewrite (PRD §7).
    Dates update (and stay flagged) on the next explicit regenerate.
    Charter wants this as an arq background job — runs synchronously until M5."""
    old_version_ids = (
        (
            await session.execute(
                select(RuleVersion.id).where(
                    RuleVersion.rule_id == rule_id, RuleVersion.id != new_version.id
                )
            )
        )
        .scalars()
        .all()
    )
    affected = (
        (
            await session.execute(
                select(CalendarRow).where(CalendarRow.rule_version_id.in_(old_version_ids))
            )
        )
        .scalars()
        .all()
    )
    for row in affected:
        row.needs_review = True
        row.needs_review_reason = NeedsReviewReason.rule_revised
        await audit.record(
            session,
            firm_id=row.firm_id,
            actor_user_id=None,  # system action: dataset update
            entity_type="calendar_row",
            entity_id=row.id,
            action="rule_revised",
            after={"new_version": new_version.version_no, "rule_id": str(rule_id)},
        )


async def main() -> None:
    """CLI: load the signed production dataset. Unsigned entries abort the run."""
    from app.db import get_engine, get_session

    get_engine()
    entries = load_dataset_files(DATASET_DIR, allow_test_only=False)
    async for session in get_session():
        summary = await load_entries(session, entries)
        print(summary)  # noqa: T201 — CLI output


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
