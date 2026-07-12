"""Calendar row persistence — every fn takes firm_id (C10)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalendarRow, ComplianceRule, RuleExtension, RuleVersion


async def rows_for_company_fy(
    session: AsyncSession, firm_id: uuid.UUID, company_id: uuid.UUID, fy: int
) -> list[CalendarRow]:
    return list(
        (
            await session.execute(
                select(CalendarRow).where(
                    CalendarRow.firm_id == firm_id,
                    CalendarRow.company_id == company_id,
                    CalendarRow.fy == fy,
                )
            )
        )
        .scalars()
        .all()
    )


async def get_row(
    session: AsyncSession, firm_id: uuid.UUID, row_id: uuid.UUID
) -> CalendarRow | None:
    return (
        await session.execute(
            select(CalendarRow).where(CalendarRow.firm_id == firm_id, CalendarRow.id == row_id)
        )
    ).scalar_one_or_none()


async def rows_with_trace(
    session: AsyncSession,
    firm_id: uuid.UUID,
    company_id: uuid.UUID,
    fy: int,
    needs_review: bool | None = None,
) -> list[tuple[CalendarRow, str, int, dict[str, Any], RuleExtension | None]]:
    """Rows joined with their pinned rule version for the trace popover:
    every date traces to rule code → version → citation (PRD §7)."""
    q = (
        select(CalendarRow, ComplianceRule.code, RuleVersion.version_no, RuleVersion.payload,
               RuleExtension)
        .join(RuleVersion, CalendarRow.rule_version_id == RuleVersion.id)
        .join(ComplianceRule, RuleVersion.rule_id == ComplianceRule.id)
        .outerjoin(RuleExtension, CalendarRow.extension_id == RuleExtension.id)
        .where(
            CalendarRow.firm_id == firm_id,
            CalendarRow.company_id == company_id,
            CalendarRow.fy == fy,
        )
        .order_by(CalendarRow.computed_due_date.nulls_last(), ComplianceRule.code)
    )
    if needs_review is not None:
        q = q.where(CalendarRow.needs_review == needs_review)
    return [tuple(r) for r in (await session.execute(q)).all()]
