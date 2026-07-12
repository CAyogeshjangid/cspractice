from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class MeetingType(str, enum.Enum):
    board = "board"
    committee = "committee"
    egm = "egm"
    agm = "agm"


class MeetingStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    held = "held"


class Meeting(IdTimestamps, Base):
    """Meeting workspace (PRD §5): one record drives the combined
    Notice/Minutes/Attendance pack via the stamped-template document engine."""

    __tablename__ = "meeting"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    fy: Mapped[int] = mapped_column(Integer, nullable=False)  # FY ending year (§9)
    meeting_type: Mapped[MeetingType] = mapped_column(
        Enum(MeetingType, name="meeting_type"), nullable=False
    )
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus, name="meeting_status"), nullable=False, default=MeetingStatus.draft
    )
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    meeting_time: Mapped[str] = mapped_column(String(20), nullable=False)
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    notice_date: Mapped[date | None] = mapped_column(Date)
    chairperson: Mapped[str | None] = mapped_column(String(200))
    agenda_items: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # participants are DIRECTOR IDs — resolved server-side from the master,
    # so attendance sheets can never contain names not on the register
    participant_director_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
