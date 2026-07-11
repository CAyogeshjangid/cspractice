from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class Letterhead(str, enum.Enum):
    company = "company"
    pcs = "pcs"
    none = "none"


class DocTemplate(IdTimestamps, Base):
    """Template registry (charter §5). Generation REFUSES templates where
    is_active is false or validated_at is null — a stamp is a gate, not advice
    (PRD §4.7)."""

    __tablename__ = "doc_template"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    governing_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # under templates/docx/
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validated_by: Mapped[str | None] = mapped_column(String(200))
    validated_membership_no: Mapped[str | None] = mapped_column(String(50))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class GeneratedDocument(IdTimestamps, Base):
    __tablename__ = "generated_document"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doc_template.id"), nullable=False
    )
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    letterhead: Mapped[Letterhead] = mapped_column(
        Enum(Letterhead, name="letterhead"), nullable=False
    )
    data_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
