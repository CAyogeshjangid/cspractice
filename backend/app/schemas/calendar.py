from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models import RowStatus


class CalendarRowOut(BaseModel):
    id: uuid.UUID
    fy: int
    category: str
    obligation_name: str
    form_number: str | None
    # traceability: every date carries its provenance (PRD §7 / charter §6)
    rule_code: str
    rule_version: int
    citation: str
    occurrence_label: str
    subject_type: str
    subject_id: uuid.UUID | None
    computed_due_date: date | None
    override_date: date | None
    override_reason: str | None
    extension_date: date | None
    extension_ref: str | None
    effective_due_date: date | None  # override > extension > computed
    status: RowStatus
    srn: str | None
    filed_offline_ack: bool
    assignee_user_id: uuid.UUID | None
    remarks: str | None
    needs_review: bool
    needs_review_reason: str | None


class RowPatch(BaseModel):
    """Everyday edits (assignee/status/SRN/remarks): Executive+ (assigned rows
    only for Executive). Overrides: Manager+. Enforced in the route."""

    status: RowStatus | None = None
    srn: str | None = Field(default=None, max_length=50)
    filed_offline_ack: bool | None = None
    remarks: str | None = None
    assignee_user_id: uuid.UUID | None = None
    override_date: date | None = None
    override_reason: str | None = Field(default=None, max_length=500)
    acknowledge_review: bool | None = None  # clears the needs_review flag


class FyAttributesIn(BaseModel):
    turnover: float | None = Field(default=None, ge=0)
    net_worth: float | None = None
    net_profit: float | None = None
    has_tan: bool | None = None
    has_gst_registration: bool | None = None
    has_transfer_pricing: bool | None = None
    has_outstanding_receipts: bool | None = None
    has_msme_dues_over_45d: bool | None = None
