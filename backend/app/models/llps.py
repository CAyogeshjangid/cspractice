"""LLP entity type — parallel masters (PRD §5 Phase 2, deliberately narrow:
masters + Form 11/8 working papers; manual data, no MCA fetch, and NO due
dates here — LLP deadlines belong to the rules dataset, C12)."""
from __future__ import annotations

from typing import Any

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class Llp(IdTimestamps, Base):
    __tablename__ = "llp"
    # LLPIN unique per firm among NON-deleted rows (partial index in migration,
    # same discipline as company CIN)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    llpin: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    registered_address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))
    fy_end_month: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    fy_end_day: Mapped[int] = mapped_column(Integer, nullable=False, default=31)
    total_contribution: Mapped[float | None] = mapped_column(Numeric(18, 2))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_reason: Mapped[str | None] = mapped_column(Text)


class LlpPartner(IdTimestamps, Base):
    __tablename__ = "llp_partner"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    llp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llp.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dpin: Mapped[str | None] = mapped_column(String(8))
    is_designated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    appointment_date: Mapped[date | None] = mapped_column(Date)
    cessation_date: Mapped[date | None] = mapped_column(Date)
    contribution: Mapped[float | None] = mapped_column(Numeric(18, 2))
    profit_share_percent: Mapped[float | None] = mapped_column(Numeric(7, 4))


class LlpForm(str, enum.Enum):
    form11 = "form11"  # Annual Return of LLP
    form8 = "form8"    # Statement of Account & Solvency


class WorkingPaperStatus(str, enum.Enum):
    draft = "draft"
    finalized = "finalized"


class LlpWorkingPaper(IdTimestamps, Base):
    """Data-assembly working paper per LLP per FY per form — a preparation
    tool for the MCA filing (which happens outside Praxis; no portal
    automation, charter 10.1). Filing deadlines live in the rules dataset."""

    __tablename__ = "llp_working_paper"
    __table_args__ = (UniqueConstraint("llp_id", "fy", "form"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    llp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llp.id"), nullable=False, index=True
    )
    fy: Mapped[int] = mapped_column(Integer, nullable=False)  # FY ending year (§9)
    form: Mapped[LlpForm] = mapped_column(Enum(LlpForm, name="llp_form"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[WorkingPaperStatus] = mapped_column(
        Enum(WorkingPaperStatus, name="working_paper_status"),
        nullable=False,
        default=WorkingPaperStatus.draft,
    )
    srn: Mapped[str | None] = mapped_column(String(50))
