"""Meeting pack generation (PRD §5): one meeting record → Notice + Minutes +
Attendance through the stamped-template engine. Participants resolve from the
directors master server-side — a pack can never name someone off the register."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Firm, Letterhead, Meeting, MeetingType
from app.repositories import masters as masters_repo
from app.services import documents as docs

MEETING_LABELS = {
    MeetingType.board: "Board Meeting",
    MeetingType.committee: "Committee Meeting",
    MeetingType.egm: "Extraordinary General Meeting",
    MeetingType.agm: "Annual General Meeting",
}

# which stamped templates make up a pack, per meeting type
PACK_TEMPLATES = {
    MeetingType.board: ("BOARD-NOTICE", "MEETING-MINUTES", "ATTENDANCE-SHEET"),
    MeetingType.committee: ("BOARD-NOTICE", "MEETING-MINUTES", "ATTENDANCE-SHEET"),
    MeetingType.egm: ("AGM-NOTICE", "MEETING-MINUTES", "ATTENDANCE-SHEET"),
    MeetingType.agm: ("AGM-NOTICE", "MEETING-MINUTES", "ATTENDANCE-SHEET"),
}


async def participant_directors(
    session: AsyncSession, firm_id: uuid.UUID, meeting: Meeting
) -> list[dict[str, str]]:
    directors = await masters_repo.list_directors(session, firm_id, meeting.company_id)
    wanted = set(meeting.participant_director_ids)
    chosen = [d for d in directors if str(d.id) in wanted] if wanted else [
        d for d in directors if d.is_active
    ]
    return [
        {
            "name": d.name,
            "din": d.din or "—",
            "designation": d.designation or "Director",
            "appointment_date": str(d.appointment_date) if d.appointment_date else "—",
        }
        for d in chosen
    ]


async def generate_pack(
    session: AsyncSession,
    firm: Firm,
    company: Company,
    meeting: Meeting,
    letterhead: Letterhead,
    signatory: dict[str, str],
    actor: uuid.UUID,
) -> list[dict[str, str]]:
    """→ [{template_code, document_id, download}] for the meeting's pack.
    Raises documents.TemplateNotUsable if any template lacks a stamp — the
    pack is all-or-nothing checked BEFORE generating anything."""
    label = MEETING_LABELS[meeting.meeting_type]
    attendees = await participant_directors(session, firm.id, meeting)

    common_params: dict[str, Any] = {
        "meeting_type": label,
        "meeting_label": label,
        "meeting_date": str(meeting.meeting_date),
        "meeting_time": meeting.meeting_time,
        "venue": meeting.venue,
        "chairperson": meeting.chairperson or (attendees[0]["name"] if attendees else "—"),
        "agenda_items": meeting.agenda_items,
        "ordinary_business": meeting.agenda_items,
        "special_business": [],
        "conclusion_time": "—",
        **signatory,
    }
    overrides: dict[str, Any] = {"directors": attendees}
    if meeting.meeting_type in (MeetingType.agm, MeetingType.egm):
        # the notice must show THIS meeting's date, not the master's AGM field;
        # server-derived, so the master-data protection stays intact
        overrides["agm_date"] = str(meeting.meeting_date)

    results = []
    for code in PACK_TEMPLATES[meeting.meeting_type]:
        doc_id, _path = await docs.generate(
            session, firm, company, code, letterhead, common_params, actor,
            context_overrides=overrides,
        )
        results.append({
            "template_code": code,
            "document_id": str(doc_id),
            "download": f"/api/v1/documents/{doc_id}/download",
        })
    return results
