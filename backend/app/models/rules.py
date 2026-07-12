from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class RuleCategory(str, enum.Enum):
    roc = "roc"
    income_tax = "income_tax"
    gst = "gst"
    # Phase 2 categories (PRD §5)
    fema = "fema"
    pf = "pf"
    esic = "esic"
    esop = "esop"


class ComplianceRule(IdTimestamps, Base):
    """Rule head. Calendars NEVER reference this — only rule_version (PRD §7)."""

    __tablename__ = "compliance_rule"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    category: Mapped[RuleCategory] = mapped_column(
        Enum(RuleCategory, name="rule_category"), nullable=False
    )
    obligation_name: Mapped[str] = mapped_column(String(300), nullable=False)
    form_number: Mapped[str | None] = mapped_column(String(50))


class RuleVersion(IdTimestamps, Base):
    """Immutable — application role has no UPDATE grant (migration enforces).

    `payload` holds the full rule at that version: applicability predicate,
    anchor fallback list, offset_spec, variants, occurrences, supersedes,
    phase (Amendment A1). The evaluator consumes payload only.
    """

    __tablename__ = "rule_version"
    __table_args__ = (UniqueConstraint("rule_id", "version_no"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_rule.id"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signed_off_by: Mapped[str] = mapped_column(String(200), nullable=False)
    signoff_note: Mapped[str | None] = mapped_column(Text)
    source_document_ref: Mapped[str] = mapped_column(Text, nullable=False)


class RuleExtension(IdTimestamps, Base):
    __tablename__ = "rule_extension"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_rule.id"), nullable=False, index=True
    )
    circular_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    circular_date: Mapped[date] = mapped_column(Date, nullable=False)
    applies_fy: Mapped[int] = mapped_column(Integer, nullable=False)
    applies_predicate: Mapped[dict | None] = mapped_column(JSONB)  # e.g. only TP cases
    extended_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    signed_off_by: Mapped[str] = mapped_column(String(200), nullable=False)
