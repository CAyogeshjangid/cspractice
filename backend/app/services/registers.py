"""Statutory register registry + append-only operations (PRD §5 Phase 2, §8).

The 14 Companies Act registers as TYPED record schemas — not generic CRUD.
Field schemas below are drafted in-house from the statute's data requirements
(charter 10.7); the reviewing professional refines them the same way rules
are reviewed — field additions are code-review events, listed per section.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RegisterEntry, RegisterType


@dataclass(frozen=True)
class RegisterSpec:
    name: str
    section: str
    mandatory: bool
    required: tuple[str, ...]
    optional: tuple[str, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        return self.required + self.optional


REGISTERS: dict[RegisterType, RegisterSpec] = {
    RegisterType.members: RegisterSpec(
        "Register of Members", "S.88(1)(a) / MGT-1", True,
        ("folio_no", "name", "shares_held", "date_of_entry"),
        ("address", "share_class", "pan", "nominee", "cessation_date", "remarks"),
    ),
    RegisterType.debenture_holders: RegisterSpec(
        "Register of Debenture Holders", "S.88(2)", False,
        ("holder_name", "debentures_held", "series"),
        ("address", "issue_date", "redemption_date", "remarks"),
    ),
    RegisterType.share_transfers: RegisterSpec(
        "Register of Transfer of Shares", "R.7 / SH-6", True,
        ("transfer_date", "transferor", "transferee", "no_of_shares"),
        ("certificate_no", "consideration", "folio_from", "folio_to", "remarks"),
    ),
    RegisterType.directors_kmp: RegisterSpec(
        "Register of Directors and KMP", "S.170", True,
        ("name", "din_or_pan", "designation", "appointment_date"),
        ("address", "cessation_date", "shareholding", "remarks"),
    ),
    RegisterType.charges: RegisterSpec(
        "Register of Charges", "S.85 / CHG-7", True,
        ("charge_holder", "amount", "creation_date", "property_description"),
        ("charge_id", "modification_date", "satisfaction_date", "remarks"),
    ),
    RegisterType.investments: RegisterSpec(
        "Register of Investments not in Company's Name", "S.187 / MBP-3", False,
        ("investee", "nature", "amount", "date"),
        ("board_resolution_ref", "remarks"),
    ),
    RegisterType.loans_guarantees: RegisterSpec(
        "Register of Loans, Guarantees and Securities", "S.186 / MBP-2", True,
        ("recipient", "nature", "amount", "date"),
        ("rate_of_interest", "purpose", "board_resolution_ref", "remarks"),
    ),
    RegisterType.related_party_contracts: RegisterSpec(
        "Register of Contracts with Related Parties", "S.189 / MBP-4", True,
        ("party", "relationship", "nature_of_contract", "date"),
        ("terms", "approval_ref", "remarks"),
    ),
    RegisterType.duplicate_share_certs: RegisterSpec(
        "Register of Renewed and Duplicate Share Certificates", "S.46 / SH-2", False,
        ("certificate_no", "folio_no", "issue_date", "reason"),
        ("original_certificate_ref", "remarks"),
    ),
    RegisterType.beneficial_interest: RegisterSpec(
        "Register of Declarations of Beneficial Interest", "S.89 / MGT-6", False,
        ("declarant", "member_name", "shares", "declaration_date"),
        ("nature_of_interest", "remarks"),
    ),
    RegisterType.deposits: RegisterSpec(
        "Register of Deposits", "S.73 / R.14", False,
        ("depositor", "amount", "receipt_date", "maturity_date"),
        ("rate_of_interest", "repayment_date", "remarks"),
    ),
    RegisterType.sweat_equity: RegisterSpec(
        "Register of Sweat Equity Shares", "S.54 / SH-3", False,
        ("allottee", "shares", "issue_date", "consideration"),
        ("lock_in_until", "board_resolution_ref", "remarks"),
    ),
    RegisterType.esop: RegisterSpec(
        "Register of Employee Stock Options", "S.62(1)(b) / SH-6", False,
        ("grantee", "options_granted", "grant_date", "exercise_price"),
        ("vesting_schedule", "options_exercised", "options_lapsed", "remarks"),
    ),
    RegisterType.buy_back: RegisterSpec(
        "Register of Shares Bought Back", "S.68 / SH-10", False,
        ("buy_back_date", "shares_bought", "price_per_share"),
        ("consideration", "cancellation_date", "board_resolution_ref", "remarks"),
    ),
}


class PayloadInvalid(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def validate_payload(register_type: RegisterType, payload: dict[str, Any]) -> None:
    spec = REGISTERS[register_type]
    problems = [
        f"missing required field: {field}"
        for field in spec.required
        if not str(payload.get(field, "")).strip()
    ]
    problems += [
        f"unknown field: {key}" for key in payload if key not in spec.fields
    ]
    if problems:
        raise PayloadInvalid(problems)


class VersionConflict(Exception):
    pass


async def current_version(
    session: AsyncSession, firm_id: uuid.UUID, entry_key: uuid.UUID
) -> RegisterEntry | None:
    return (
        await session.execute(
            select(RegisterEntry)
            .where(RegisterEntry.firm_id == firm_id, RegisterEntry.entry_key == entry_key)
            .order_by(RegisterEntry.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_entry(
    session: AsyncSession,
    firm_id: uuid.UUID,
    company_id: uuid.UUID,
    register_type: RegisterType,
    payload: dict[str, Any],
    actor: uuid.UUID,
) -> RegisterEntry:
    validate_payload(register_type, payload)
    entry = RegisterEntry(
        firm_id=firm_id,
        company_id=company_id,
        register_type=register_type,
        payload=payload,
        created_by=actor,
    )
    session.add(entry)
    await session.flush()
    return entry


async def amend_entry(
    session: AsyncSession,
    firm_id: uuid.UUID,
    entry_key: uuid.UUID,
    payload: dict[str, Any],
    expected_version: int,
    actor: uuid.UUID,
) -> RegisterEntry:
    """Append a new version (never UPDATE — the grant forbids it anyway).
    Optimistic concurrency: the caller states which version it amended."""
    head = await current_version(session, firm_id, entry_key)
    if head is None:
        raise LookupError("entry not found")
    if head.is_deleted:
        raise VersionConflict("entry is deleted; restore is not supported for legal records")
    if head.version_no != expected_version:
        raise VersionConflict(
            f"entry changed since you loaded it (head is v{head.version_no}, "
            f"you amended v{expected_version}) — reload and re-apply"
        )
    validate_payload(head.register_type, payload)
    entry = RegisterEntry(
        firm_id=firm_id,
        company_id=head.company_id,
        register_type=head.register_type,
        entry_key=entry_key,
        version_no=head.version_no + 1,
        payload=payload,
        created_by=actor,
    )
    session.add(entry)
    await session.flush()
    return entry


async def soft_delete_entry(
    session: AsyncSession,
    firm_id: uuid.UUID,
    entry_key: uuid.UUID,
    reason: str,
    actor: uuid.UUID,
) -> RegisterEntry:
    """Delete = a VERSION EVENT: a new version flagged is_deleted, reason
    mandatory; every prior version stays in the history view (PRD §8)."""
    head = await current_version(session, firm_id, entry_key)
    if head is None:
        raise LookupError("entry not found")
    if head.is_deleted:
        raise VersionConflict("entry is already deleted")
    entry = RegisterEntry(
        firm_id=firm_id,
        company_id=head.company_id,
        register_type=head.register_type,
        entry_key=entry_key,
        version_no=head.version_no + 1,
        payload=head.payload,
        is_deleted=True,
        delete_reason=reason,
        created_by=actor,
    )
    session.add(entry)
    await session.flush()
    return entry


async def entries_as_on(
    session: AsyncSession,
    firm_id: uuid.UUID,
    company_id: uuid.UUID,
    register_type: RegisterType,
    as_on: datetime | None = None,
) -> list[RegisterEntry]:
    """Point-in-time view: the latest version of each entry as of `as_on`
    (default: now), excluding entries deleted by then. This is what makes an
    'as on date' register extract possible (PRD §8 export stamp)."""
    q = select(RegisterEntry).where(
        RegisterEntry.firm_id == firm_id,
        RegisterEntry.company_id == company_id,
        RegisterEntry.register_type == register_type,
    )
    if as_on is not None:
        q = q.where(RegisterEntry.created_at <= as_on)
    rows = (await session.execute(q.order_by(RegisterEntry.created_at))).scalars().all()
    heads: dict[uuid.UUID, RegisterEntry] = {}
    for row in rows:  # ordered by time: the last seen per key is the head as-on
        heads[row.entry_key] = row
    return [e for e in heads.values() if not e.is_deleted]


async def history(
    session: AsyncSession, firm_id: uuid.UUID, entry_key: uuid.UUID
) -> list[RegisterEntry]:
    return list(
        (
            await session.execute(
                select(RegisterEntry)
                .where(RegisterEntry.firm_id == firm_id, RegisterEntry.entry_key == entry_key)
                .order_by(RegisterEntry.version_no)
            )
        )
        .scalars()
        .all()
    )
