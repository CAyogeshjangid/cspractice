"""Practice-level masters (PRD §5 Phase 2): auditors, PCS, DSC tokens.

Charges deliberately have NO table here — the §85 Register of Charges
(append-only, M9) is the legal record; duplicating it as a mutable master
would create two sources of truth for the same facts.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class Auditor(IdTimestamps, Base):
    """CA firm master, reusable across client engagements."""

    __tablename__ = "auditor"
    __table_args__ = (UniqueConstraint("firm_id", "frn"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    firm_name: Mapped[str] = mapped_column(String(200), nullable=False)
    frn: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))


class AuditorAppointment(IdTimestamps, Base):
    __tablename__ = "auditor_appointment"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    auditor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auditor.id"), nullable=False, index=True
    )
    appointed_from_fy: Mapped[int] = mapped_column(Integer, nullable=False)
    appointed_to_fy: Mapped[int | None] = mapped_column(Integer)  # open = current auditor
    adt1_srn: Mapped[str | None] = mapped_column(String(50))
    remarks: Mapped[str | None] = mapped_column(Text)


class PcsProfessional(IdTimestamps, Base):
    """Practicing CS master — feeds letterheads and signing blocks."""

    __tablename__ = "pcs_professional"
    __table_args__ = (UniqueConstraint("firm_id", "membership_no"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    membership_no: Mapped[str] = mapped_column(String(20), nullable=False)
    cop_no: Mapped[str | None] = mapped_column(String(20))
    firm_name: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320))


class DscToken(IdTimestamps, Base):
    """Digital Signature Certificate token tracker (physical token custody)."""

    __tablename__ = "dsc_token"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    holder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    director_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("director.id")
    )
    token_color: Mapped[str | None] = mapped_column(String(30))
    token_number: Mapped[str | None] = mapped_column(String(50))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)
