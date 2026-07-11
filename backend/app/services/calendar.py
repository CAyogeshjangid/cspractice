"""Calendar generation: evaluator drafts → persisted rows (charter §6, M4).

Rules of persistence:
- Rows are upserted by (rule, subject, occurrence). User state — status,
  assignee, SRN, remarks, overrides — is ALWAYS preserved on regenerate.
- A changed computed date on a row the user has seen is applied AND flagged
  needs_review/rule_revised ("date revised — review"), never silent (PRD §7).
- No due-date math happens here — that is the evaluator's job alone (C12).
"""
from __future__ import annotations

import uuid
from typing import Any

from dataclasses import replace as dc_replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app import audit
from app.models import (
    CalendarRow,
    Company,
    CompanyFyAttributes,
    ComplianceRule,
    NeedsReviewReason,
    RuleVersion,
    SubjectType,
)
from app.repositories import calendar as cal_repo
from app.repositories import masters as masters_repo
from app.repositories import rules as rules_repo
from app.rules.dates import fy_end
from app.rules.evaluator import CalendarRowDraft, Extension, RuleData, compute_calendar


async def _attribute_bag(
    session: AsyncSession, firm_id: uuid.UUID, company: Company, fys: list[int]
) -> dict[int, dict[str, Any]]:
    """Company columns + per-FY facts (spike G1). Missing values stay absent →
    predicates resolve UNKNOWN → needs_review, never silently false."""
    base = {
        "entity_type": "company",
        "category": (company.category or "").lower() or None,
        "is_listed": company.is_listed,
        "paidup_capital": float(company.paidup_capital) if company.paidup_capital else None,
    }
    bag: dict[int, dict[str, Any]] = {}
    rows = (
        await session.execute(
            select(CompanyFyAttributes).where(
                CompanyFyAttributes.firm_id == firm_id,
                CompanyFyAttributes.company_id == company.id,
                CompanyFyAttributes.fy.in_(fys),
            )
        )
    ).scalars()
    per_fy = {r.fy: r for r in rows}
    for fy in fys:
        attrs = {k: v for k, v in base.items() if v is not None}
        facts = per_fy.get(fy)
        if facts:
            for field in ("turnover", "net_worth", "net_profit"):
                value = getattr(facts, field)
                if value is not None:
                    attrs[field] = float(value)
            for field in (
                "has_tan", "has_gst_registration", "has_transfer_pricing",
                "has_outstanding_receipts", "has_msme_dues_over_45d",
            ):
                value = getattr(facts, field)
                if value is not None:
                    attrs[field] = value
        bag[fy] = attrs
    return bag


async def generate(
    session: AsyncSession,
    firm_id: uuid.UUID,
    company: Company,
    fy: int,
    actor_user_id: uuid.UUID,
    request: Request | None = None,
) -> dict[str, int]:
    versions = await rules_repo.effective_versions_for_fy(session, fy)
    rules = [
        RuleData.from_payload(code, v.version_no, v.payload) for code, v in versions
    ]
    version_ids = {(code, v.version_no): v.id for code, v in versions}

    ext_pairs = await rules_repo.extensions_for_fy(session, fy)
    extensions = [
        Extension(
            rule_code=code,
            circular_ref=ext.circular_ref,
            applies_fy=ext.applies_fy,
            applies_predicate=ext.applies_predicate,
            extended_due_date=ext.extended_due_date,
        )
        for code, ext in ext_pairs
    ]
    extension_ids = {ext.circular_ref: ext.id for _code, ext in ext_pairs}

    company_dict = {"agm_date": company.agm_date}
    attrs = await _attribute_bag(session, firm_id, company, [fy, fy - 1])
    drafts = compute_calendar(company_dict, attrs, fy, rules, extensions)
    drafts = await _expand_director_subjects(session, firm_id, company.id, fy, drafts)

    # Index existing rows by RULE CODE (not version id) so a version bump
    # finds and revises its predecessor row instead of duplicating it.
    existing_rows = await cal_repo.rows_for_company_fy(session, firm_id, company.id, fy)
    all_versions = (
        await session.execute(
            select(RuleVersion.id, ComplianceRule.code).join(
                ComplianceRule, RuleVersion.rule_id == ComplianceRule.id
            )
        )
    ).all()
    version_code = {vid: code for vid, code in all_versions}
    by_code: dict[tuple[str, uuid.UUID | None, str], CalendarRow] = {
        (version_code[row.rule_version_id], row.subject_id, row.occurrence_label): row
        for row in existing_rows
    }

    created = updated = revised = unchanged = 0
    for draft in drafts:
        vid = version_ids[(draft.rule_code, draft.rule_version)]
        subject_id = draft.subject_id
        key = (draft.rule_code, subject_id, draft.occurrence_label)
        row = by_code.get(key)
        if row is None:
            session.add(
                CalendarRow(
                    firm_id=firm_id,
                    company_id=company.id,
                    fy=fy,
                    rule_version_id=vid,
                    subject_type=SubjectType(draft.subject_type),
                    subject_id=subject_id,
                    occurrence_label=draft.occurrence_label,
                    computed_due_date=draft.computed_due_date,
                    extension_id=extension_ids.get(draft.extension_ref),
                    needs_review=draft.needs_review,
                    needs_review_reason=(
                        NeedsReviewReason(draft.needs_review_reason)
                        if draft.needs_review_reason
                        else None
                    ),
                )
            )
            created += 1
            continue

        # existing row: preserve user state; apply date/version/flag changes
        changed = False
        if row.rule_version_id != vid:
            row.rule_version_id = vid
            changed = True
        if row.computed_due_date != draft.computed_due_date:
            before = str(row.computed_due_date)
            row.computed_due_date = draft.computed_due_date
            row.needs_review = True
            row.needs_review_reason = NeedsReviewReason.rule_revised
            await audit.record(
                session, firm_id=firm_id, actor_user_id=actor_user_id,
                entity_type="calendar_row", entity_id=row.id, action="date_revised",
                before={"computed_due_date": before},
                after={"computed_due_date": str(draft.computed_due_date)},
                request=request,
            )
            revised += 1
            continue
        if draft.needs_review and not row.needs_review:
            row.needs_review = True
            row.needs_review_reason = (
                NeedsReviewReason(draft.needs_review_reason)
                if draft.needs_review_reason
                else None
            )
            changed = True
        new_ext = extension_ids.get(draft.extension_ref)
        if new_ext and row.extension_id != new_ext:
            row.extension_id = new_ext
            changed = True
        updated += 1 if changed else 0
        unchanged += 0 if changed else 1

    await audit.record(
        session, firm_id=firm_id, actor_user_id=actor_user_id, entity_type="company",
        entity_id=company.id, action="calendar_generate",
        after={"fy": fy, "created": created, "revised": revised}, request=request,
    )
    await session.commit()
    return {"created": created, "updated": updated, "revised": revised, "unchanged": unchanged}


async def _expand_director_subjects(
    session: AsyncSession,
    firm_id: uuid.UUID,
    company_id: uuid.UUID,
    fy: int,
    drafts: list[CalendarRowDraft],
) -> list[CalendarRowDraft]:
    """subject: director rules (DIR-3 KYC) become one row per in-office director
    (spike G6). DIN allocated after FY end → not applicable this FY; DIN present
    but allocation date unknown → row flagged for review, never guessed."""
    out: list[CalendarRowDraft] = []
    directors = None
    for draft in drafts:
        if draft.subject_type != "director":
            out.append(draft)
            continue
        if directors is None:
            directors = await masters_repo.list_directors(session, firm_id, company_id, fy=fy)
        for director in directors:
            if not director.din:
                continue
            clone = dc_replace(draft, subject_id=director.id)
            if director.din_allocation_date is None:
                clone.needs_review = True
                clone.needs_review_reason = "applicability_unknown"
            elif director.din_allocation_date > fy_end(fy):
                continue
            out.append(clone)
    return out
