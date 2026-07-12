from __future__ import annotations

from typing import Any

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestamps


class Role(str, enum.Enum):
    partner = "partner"
    manager = "manager"
    executive = "executive"
    viewer = "viewer"


class Firm(IdTimestamps, Base):
    __tablename__ = "firm"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="pilot")
    # email provider config etc.; secrets in this blob are envelope-encrypted (C8)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class User(IdTimestamps, Base):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("firm_id", "email"),)

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Invitation(IdTimestamps, Base):
    __tablename__ = "invitation"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
