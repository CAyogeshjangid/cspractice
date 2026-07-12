from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RegisterType(str, enum.Enum):
    members = "members"                        # §88
    debenture_holders = "debenture_holders"    # §88(2)
    share_transfers = "share_transfers"        # r.7 / SH-6
    directors_kmp = "directors_kmp"            # §170
    charges = "charges"                        # §85
    investments = "investments"                # §186
    loans_guarantees = "loans_guarantees"      # §186
    related_party_contracts = "related_party_contracts"  # §189
    duplicate_share_certs = "duplicate_share_certs"      # §46
    beneficial_interest = "beneficial_interest"          # §89
    deposits = "deposits"                      # §73
    sweat_equity = "sweat_equity"              # §54
    esop = "esop"                              # §62(1)(b)
    buy_back = "buy_back"                      # §68


class RegisterEntry(Base):
    """Statutory register record — APPEND-ONLY (PRD §8).

    Registers under §§88/170/189 etc. are legal records, therefore:
    - An entry's identity is `entry_key`; every edit INSERTs version_no + 1.
    - "Delete" is a new version with is_deleted=true and a mandatory reason —
      the row remains in the register's full history view forever.
    - The application role has NO UPDATE/DELETE grant on this table
      (enforced in the migration, verified by the pre-launch test suite).
    There is deliberately no updated_at: rows are never updated.
    """

    __tablename__ = "register_entry"
    __table_args__ = (UniqueConstraint("entry_key", "version_no"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    register_type: Mapped[RegisterType] = mapped_column(
        Enum(RegisterType, name="register_type"), nullable=False, index=True
    )
    entry_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, default=uuid.uuid4
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delete_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
