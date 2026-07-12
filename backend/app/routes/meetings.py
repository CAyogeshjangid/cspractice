"""Meeting scheduler routes (PRD §5 Phase 2)."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import (
    Firm,
    Letterhead,
    Meeting,
    MeetingStatus,
    MeetingType,
    Role,
    User,
)
from app.repositories import companies as companies_repo
from app.security.auth import require_role
from app.services import documents as docs
from app.services import meetings as svc

router = APIRouter(prefix="/api/v1", tags=["meetings"])


class MeetingIn(BaseModel):
    fy: int
    meeting_type: MeetingType
    meeting_date: date
    meeting_time: str = Field(min_length=1, max_length=20)
    venue: str = Field(min_length=3)
    notice_date: date | None = None
    chairperson: str | None = None
    agenda_items: list[str] = Field(default_factory=list, max_length=50)
    participant_director_ids: list[str] = Field(default_factory=list, max_length=50)
    status: MeetingStatus = MeetingStatus.draft


class PackIn(BaseModel):
    letterhead: Letterhead = Letterhead.company
    signatory_name: str = Field(min_length=1, max_length=200)
    signatory_designation: str = Field(min_length=1, max_length=100)
    place: str = Field(min_length=1, max_length=100)


def _out(m: Meeting) -> dict:
    return {
        "id": str(m.id),
        "fy": m.fy,
        "meeting_type": m.meeting_type.value,
        "status": m.status.value,
        "meeting_date": str(m.meeting_date),
        "meeting_time": m.meeting_time,
        "venue": m.venue,
        "notice_date": str(m.notice_date) if m.notice_date else None,
        "chairperson": m.chairperson,
        "agenda_items": m.agenda_items,
        "participant_director_ids": m.participant_director_ids,
    }


async def _owned_company(session: AsyncSession, user: User, company_id: uuid.UUID):
    company = await companies_repo.get_company(session, user.firm_id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return company


async def _owned_meeting(session: AsyncSession, user: User, meeting_id: uuid.UUID) -> Meeting:
    meeting = (
        await session.execute(
            select(Meeting).where(Meeting.firm_id == user.firm_id, Meeting.id == meeting_id)
        )
    ).scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    return meeting


@router.get("/companies/{company_id}/meetings")
async def list_meetings(
    company_id: uuid.UUID,
    fy: int | None = None,
    meeting_type: MeetingType | None = None,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _owned_company(session, user, company_id)
    q = select(Meeting).where(
        Meeting.firm_id == user.firm_id, Meeting.company_id == company_id
    )
    if fy is not None:
        q = q.where(Meeting.fy == fy)
    if meeting_type is not None:
        q = q.where(Meeting.meeting_type == meeting_type)
    rows = (await session.execute(q.order_by(Meeting.meeting_date))).scalars().all()
    return [_out(m) for m in rows]


@router.post("/companies/{company_id}/meetings", status_code=201)
async def create_meeting(
    company_id: uuid.UUID,
    body: MeetingIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _owned_company(session, user, company_id)
    meeting = Meeting(
        firm_id=user.firm_id, company_id=company_id, created_by=user.id,
        **body.model_dump(),
    )
    session.add(meeting)
    await session.flush()
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="meeting",
        entity_id=meeting.id, action="create",
        after={"type": body.meeting_type.value, "date": str(body.meeting_date), "fy": body.fy},
        request=request,
    )
    await session.commit()
    return _out(meeting)


@router.put("/meetings/{meeting_id}")
async def update_meeting(
    meeting_id: uuid.UUID,
    body: MeetingIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await _owned_meeting(session, user, meeting_id)
    before, after = {}, {}
    for key, value in body.model_dump().items():
        current = getattr(meeting, key)
        if current != value:
            before[key], after[key] = str(current), str(value)
            setattr(meeting, key, value)
    if after:
        await audit.record(
            session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="meeting",
            entity_id=meeting.id, action="update", before=before, after=after, request=request,
        )
        await session.commit()
    return _out(meeting)


@router.post("/meetings/{meeting_id}/pack", status_code=201)
async def generate_pack(
    meeting_id: uuid.UUID,
    body: PackIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meeting = await _owned_meeting(session, user, meeting_id)
    company = await _owned_company(session, user, meeting.company_id)
    firm = (await session.execute(select(Firm).where(Firm.id == user.firm_id))).scalar_one()
    try:
        documents = await svc.generate_pack(
            session, firm, company, meeting, body.letterhead,
            {"signatory_name": body.signatory_name,
             "signatory_designation": body.signatory_designation,
             "place": body.place},
            user.id,
        )
    except docs.TemplateNotUsable as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except docs.MissingContext as exc:
        raise HTTPException(status_code=422, detail={"title": "missing merge fields",
                                                     "missing": exc.missing})
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="meeting",
        entity_id=meeting.id, action="pack_generated",
        after={"documents": [d["template_code"] for d in documents]}, request=request,
    )
    await session.commit()
    return {"meeting_id": str(meeting_id), "documents": documents}
