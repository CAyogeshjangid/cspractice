from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class ProfessionalGroup(IdTimestamps, Base):
    __tablename__ = "professional_group"
    __table_args__ = (UniqueConstraint("firm_id", "name"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Industry(IdTimestamps, Base):
    __tablename__ = "industry"
    __table_args__ = (UniqueConstraint("firm_id", "name"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Company(IdTimestamps, Base):
    __tablename__ = "company"
    # CIN unique per firm among NON-deleted rows (REVIEW.md F8): enforced by a
    # partial unique index in the migration:
    #   CREATE UNIQUE INDEX uq_company_firm_cin ON company (firm_id, cin)
    #   WHERE deleted_at IS NULL;

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    cin: Mapped[str] = mapped_column(String(21), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(50))
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(50))
    registered_address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))
    professional_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professional_group.id")
    )
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industry.id")
    )
    fy_end_month: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    fy_end_day: Mapped[int] = mapped_column(Integer, nullable=False, default=31)
    agm_date: Mapped[date | None] = mapped_column(Date)
    is_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    authorised_capital: Mapped[float | None] = mapped_column(Numeric(18, 2))
    subscribed_capital: Mapped[float | None] = mapped_column(Numeric(18, 2))
    paidup_capital: Mapped[float | None] = mapped_column(Numeric(18, 2))
    # Soft delete only — Partner role, with reason (charter: never hard delete)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_reason: Mapped[str | None] = mapped_column(Text)


class CompanyFyAttributes(IdTimestamps, Base):
    """Per-FY facts for applicability predicates (Amendment A1 / spike G1).

    All nullable: null means UNKNOWN, which makes predicates emit
    needs_review rows rather than silently dropping obligations.
    """

    __tablename__ = "company_fy_attributes"
    __table_args__ = (UniqueConstraint("company_id", "fy"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    fy: Mapped[int] = mapped_column(Integer, nullable=False)  # FY ending year (§9)
    turnover: Mapped[float | None] = mapped_column(Numeric(18, 2))
    net_worth: Mapped[float | None] = mapped_column(Numeric(18, 2))
    net_profit: Mapped[float | None] = mapped_column(Numeric(18, 2))
    has_tan: Mapped[bool | None] = mapped_column(Boolean)
    has_gst_registration: Mapped[bool | None] = mapped_column(Boolean)
    has_transfer_pricing: Mapped[bool | None] = mapped_column(Boolean)
    has_outstanding_receipts: Mapped[bool | None] = mapped_column(Boolean)  # DPT-3
    has_msme_dues_over_45d: Mapped[bool | None] = mapped_column(Boolean)  # MSME-1


class Director(IdTimestamps, Base):
    __tablename__ = "director"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    din: Mapped[str | None] = mapped_column(String(8))
    din_status: Mapped[str | None] = mapped_column(String(50))
    din_allocation_date: Mapped[date | None] = mapped_column(Date)  # DIR-3 KYC anchor
    designation: Mapped[str | None] = mapped_column(String(100))
    appointment_date: Mapped[date | None] = mapped_column(Date)
    cessation_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DirectorDisclosure(IdTimestamps, Base):
    __tablename__ = "director_disclosure"
    __table_args__ = (UniqueConstraint("director_id", "fy"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    director_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("director.id"), nullable=False, index=True
    )
    fy: Mapped[int] = mapped_column(Integer, nullable=False)
    mbp1_received: Mapped[date | None] = mapped_column(Date)
    dir8_received: Mapped[date | None] = mapped_column(Date)
    dir2_received: Mapped[date | None] = mapped_column(Date)


class Shareholder(IdTimestamps, Base):
    __tablename__ = "shareholder"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    folio: Mapped[str | None] = mapped_column(String(50))
    shares: Mapped[float | None] = mapped_column(Numeric(18, 0))  # NUMERIC, never float (§9)
    percentage: Mapped[float | None] = mapped_column(Numeric(7, 4))
    category: Mapped[str | None] = mapped_column(String(100))
