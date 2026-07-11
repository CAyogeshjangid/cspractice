from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DirectorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    din: str | None = Field(default=None, min_length=8, max_length=8)
    din_status: str | None = None
    din_allocation_date: date | None = None
    designation: str | None = None
    appointment_date: date | None = None
    cessation_date: date | None = None
    is_active: bool = True


class DirectorOut(DirectorIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID


class DisclosureIn(BaseModel):
    mbp1_received: date | None = None
    dir8_received: date | None = None
    dir2_received: date | None = None


class DisclosureOut(DisclosureIn):
    model_config = ConfigDict(from_attributes=True)
    director_id: uuid.UUID
    fy: int


class ShareholderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    folio: str | None = None
    shares: Decimal | None = Field(default=None, ge=0)
    percentage: Decimal | None = Field(default=None, ge=0, le=100)
    category: str | None = None


class ShareholderOut(ShareholderIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID


class TaxonomyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TaxonomyOut(TaxonomyIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class CompanyUpdate(BaseModel):
    """Partial update — only provided fields change; audit records the diff."""

    name: str | None = Field(default=None, min_length=1, max_length=300)
    registration_number: str | None = None
    incorporation_date: date | None = None
    category: str | None = None
    status: str | None = None
    registered_address: str | None = None
    email: str | None = None
    phone: str | None = None
    professional_group_id: uuid.UUID | None = None
    industry_id: uuid.UUID | None = None
    fy_end_month: int | None = Field(default=None, ge=1, le=12)
    fy_end_day: int | None = Field(default=None, ge=1, le=31)
    agm_date: date | None = None
    is_listed: bool | None = None
    authorised_capital: Decimal | None = None
    subscribed_capital: Decimal | None = None
    paidup_capital: Decimal | None = None
