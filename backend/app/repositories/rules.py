"""Rules dataset access. Rules are GLOBAL (no firm_id) — one professionally
signed dataset serves every tenant; calendars reference immutable versions."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ComplianceRule, RuleExtension, RuleVersion
from app.rules.dates import fy_end


async def get_rule_by_code(session: AsyncSession, code: str) -> ComplianceRule | None:
    return (
        await session.execute(select(ComplianceRule).where(ComplianceRule.code == code))
    ).scalar_one_or_none()


async def latest_version(session: AsyncSession, rule_id: uuid.UUID) -> RuleVersion | None:
    return (
        await session.execute(
            select(RuleVersion)
            .where(RuleVersion.rule_id == rule_id)
            .order_by(RuleVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def effective_versions_for_fy(
    session: AsyncSession, fy: int
) -> list[tuple[str, RuleVersion]]:
    """(rule_code, version) pairs: per rule, the highest version_no whose
    effective_from is on or before the FY end. Calendars pin these ids."""
    rows = (
        await session.execute(
            select(ComplianceRule.code, RuleVersion)
            .join(RuleVersion, RuleVersion.rule_id == ComplianceRule.id)
            .where(RuleVersion.effective_from <= fy_end(fy))
            .order_by(ComplianceRule.code, RuleVersion.version_no.desc())
        )
    ).all()
    chosen: dict[str, RuleVersion] = {}
    for code, version in rows:
        if code not in chosen:  # first seen = highest version_no per code
            chosen[code] = version
    return list(chosen.items())


async def extensions_for_fy(
    session: AsyncSession, fy: int
) -> list[tuple[str, RuleExtension]]:
    rows = (
        await session.execute(
            select(ComplianceRule.code, RuleExtension)
            .join(RuleExtension, RuleExtension.rule_id == ComplianceRule.id)
            .where(RuleExtension.applies_fy == fy)
        )
    ).all()
    return [(code, ext) for code, ext in rows]


async def insert_version(
    session: AsyncSession,
    rule: ComplianceRule,
    version_no: int,
    effective_from: date,
    payload: dict[str, Any],
    signed_off_by: str,
    signoff_note: str | None,
    source_document_ref: str,
) -> RuleVersion:
    version = RuleVersion(
        rule_id=rule.id,
        version_no=version_no,
        effective_from=effective_from,
        payload=payload,
        signed_off_by=signed_off_by,
        signoff_note=signoff_note,
        source_document_ref=source_document_ref,
    )
    session.add(version)
    await session.flush()
    return version
