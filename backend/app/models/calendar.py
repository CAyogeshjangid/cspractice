from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class RowStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    filed = "filed"
    not_applicable = "not_applicable"


class SubjectType(str, enum.Enum):  # Amendment A1 / spike G6
    company = "company"
    director = "director"


class NeedsReviewReason(str, enum.Enum):  # Amendment A1
    missing_anchor = "missing_anchor"
    applicability_unknown = "applicability_unknown"
    rule_revised = "rule_revised"


class CalendarRow(IdTimestamps, Base):
    __tablename__ = "calendar_row"
    __table_args__ = (
        # One row per rule-version occurrence per subject per FY
        UniqueConstraint("company_id", "fy", "rule_version_id", "subject_id", "occurrence_label"),
    )

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    fy: Mapped[int] = mapped_column(Integer, nullable=False)  # FY ending year
    # A row can never exist without a rule_version FK (M4 acceptance).
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_version.id"), nullable=False
    )
    subject_type: Mapped[SubjectType] = mapped_column(
        Enum(SubjectType, name="subject_type"), nullable=False, default=SubjectType.company
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # director id etc.
    occurrence_label: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    computed_due_date: Mapped[date | None] = mapped_column(Date)  # null → needs_review
    override_date: Mapped[date | None] = mapped_column(Date)
    override_reason: Mapped[str | None] = mapped_column(Text)
    extension_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_extension.id")
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id")
    )
    status: Mapped[RowStatus] = mapped_column(
        Enum(RowStatus, name="row_status"), nullable=False, default=RowStatus.pending
    )
    srn: Mapped[str | None] = mapped_column(String(50))
    filed_offline_ack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remarks: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_review_reason: Mapped[NeedsReviewReason | None] = mapped_column(
        Enum(NeedsReviewReason, name="needs_review_reason")
    )


class ReminderConfig(IdTimestamps, Base):
    __tablename__ = "reminder_config"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    calendar_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calendar_row.id"), nullable=False, unique=True
    )
    days_before: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    extra_emails: Mapped[list[str]] = mapped_column(ARRAY(String(320)), nullable=False, default=list)


class DispatchStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"
    dead = "dead"


class ReminderDispatch(IdTimestamps, Base):
    __tablename__ = "reminder_dispatch"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    reminder_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reminder_config.id"), nullable=False, index=True
    )
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[date | None] = mapped_column(Date)
    provider: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[DispatchStatus] = mapped_column(
        Enum(DispatchStatus, name="dispatch_status"), nullable=False, default=DispatchStatus.queued
    )
    error: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
