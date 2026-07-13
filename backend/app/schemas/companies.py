from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CompanyIn(BaseModel):
    cin: str = Field(min_length=21, max_length=21)
    name: str = Field(min_length=1, max_length=300)
    registration_number: str | None = None
    incorporation_date: date | None = None
    category: str | None = None
    status: str | None = None
    registered_address: str | None = None
    email: str | None = None
    phone: str | None = None
    fy_end_month: int = Field(default=3, ge=1, le=12)
    fy_end_day: int = Field(default=31, ge=1, le=31)
    agm_date: date | None = None
    is_listed: bool = False
    authorised_capital: float | None = None
    subscribed_capital: float | None = None
    paidup_capital: float | None = None


class CompanyOut(CompanyIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    # settable via CompanyUpdate; surfaced here so the UI can show the tags
    professional_group_id: uuid.UUID | None = None
    industry_id: uuid.UUID | None = None


class DeleteIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
