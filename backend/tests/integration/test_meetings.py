"""M10 — meeting scheduler: CRUD + FY filter + combined document packs."""
from __future__ import annotations

import io

from docx import Document

from tests.conftest import post, register_firm

COMPANY = {"cin": "U74999MH2020PTC565656", "name": "Meetings Fixture Pvt Ltd",
           "registered_address": "1 Boardroom Lane, Pune", "agm_date": "2026-09-30"}

MEETING = {
    "fy": 2026,
    "meeting_type": "board",
    "meeting_date": "2026-06-15",
    "meeting_time": "11:00 AM",
    "venue": "Registered Office, Pune",
    "chairperson": "A. Chair",
    "agenda_items": ["Approve draft accounts.", "Note statutory registers."],
}


async def setup(firm) -> tuple[str, list[str]]:
    """→ (company_id, [director ids]) with templates synced + stamped."""
    import app.db as dbmod
    from app.services.documents import sync_templates

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        await sync_templates(session)
    for code in ("BOARD-NOTICE", "AGM-NOTICE", "MEETING-MINUTES", "ATTENDANCE-SHEET"):
        res = await post(firm.manager, f"/templates/{code}/validate",
                         {"validated_by": "P. Professional", "membership_no": "F1234"},
                         method="PUT")
        assert res.status_code == 200

    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    director_ids = []
    for name in ("A. Chair", "B. Member", "C. Absent"):
        res = await post(firm.manager, f"/companies/{cid}/directors",
                         {"name": name, "din": f"0{abs(hash(name)) % 10**7:07d}"})
        director_ids.append(res.json()["id"])
    return cid, director_ids


def docx_text(content: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(content)).paragraphs)


async def test_meeting_crud_and_filters(firm) -> None:
    cid, _ = await setup(firm)
    created = (await post(firm.executive, f"/companies/{cid}/meetings", MEETING)).json()
    await post(firm.executive, f"/companies/{cid}/meetings",
               {**MEETING, "meeting_type": "agm", "meeting_date": "2026-09-30", "fy": 2027})

    all_rows = (await firm.viewer.get(f"/api/v1/companies/{cid}/meetings")).json()
    assert len(all_rows) == 2
    fy26 = (await firm.viewer.get(f"/api/v1/companies/{cid}/meetings?fy=2026")).json()
    assert [m["meeting_type"] for m in fy26] == ["board"]
    agms = (await firm.viewer.get(
        f"/api/v1/companies/{cid}/meetings?meeting_type=agm")).json()
    assert len(agms) == 1

    res = await post(firm.manager, f"/meetings/{created['id']}",
                     {**MEETING, "status": "scheduled"}, method="PUT")
    assert res.json()["status"] == "scheduled"


async def test_board_pack_generates_three_docs_with_participants_only(firm) -> None:
    cid, directors = await setup(firm)
    meeting = (await post(firm.executive, f"/companies/{cid}/meetings",
                          {**MEETING, "participant_director_ids": directors[:2]})).json()

    res = await post(firm.executive, f"/meetings/{meeting['id']}/pack", {
        "letterhead": "company", "signatory_name": "R. Sharma",
        "signatory_designation": "CS", "place": "Pune",
    })
    assert res.status_code == 201, res.text
    documents = res.json()["documents"]
    assert [d["template_code"] for d in documents] == [
        "BOARD-NOTICE", "MEETING-MINUTES", "ATTENDANCE-SHEET",
    ]

    # attendance carries ONLY the selected participants, from the register
    attendance = next(d for d in documents if d["template_code"] == "ATTENDANCE-SHEET")
    text = docx_text((await firm.viewer.get(attendance["download"])).content)
    assert "A. Chair" in text and "B. Member" in text
    assert "C. Absent" not in text
    assert "{{" not in text

    # notice carries the meeting facts
    notice = next(d for d in documents if d["template_code"] == "BOARD-NOTICE")
    text = docx_text((await firm.viewer.get(notice["download"])).content)
    assert "2026-06-15" in text and "11:00 AM" in text
    assert "Approve draft accounts." in text

    # all three landed in the company's document library
    library = (await firm.viewer.get(f"/api/v1/companies/{cid}/documents")).json()
    assert len(library) == 3


async def test_agm_pack_uses_agm_notice_with_meeting_date(firm) -> None:
    cid, directors = await setup(firm)
    meeting = (await post(firm.executive, f"/companies/{cid}/meetings", {
        **MEETING, "meeting_type": "agm", "meeting_date": "2026-09-30",
        "participant_director_ids": directors,
    })).json()
    res = await post(firm.manager, f"/meetings/{meeting['id']}/pack", {
        "letterhead": "none", "signatory_name": "R. Sharma",
        "signatory_designation": "CS", "place": "Pune",
    })
    assert res.status_code == 201, res.text
    codes = [d["template_code"] for d in res.json()["documents"]]
    assert codes[0] == "AGM-NOTICE"
    notice = res.json()["documents"][0]
    text = docx_text((await firm.viewer.get(notice["download"])).content)
    assert "ANNUAL GENERAL MEETING" in text
    assert "2026-09-30" in text


async def test_pack_refuses_unstamped_template(firm) -> None:
    import app.db as dbmod
    from app.services.documents import sync_templates

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        await sync_templates(session)  # synced but NOT stamped
    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    meeting = (await post(firm.executive, f"/companies/{cid}/meetings", MEETING)).json()
    res = await post(firm.executive, f"/meetings/{meeting['id']}/pack", {
        "letterhead": "none", "signatory_name": "R", "signatory_designation": "CS",
        "place": "Pune",
    })
    assert res.status_code == 422
    assert "validation stamp" in res.json()["detail"]


async def test_meetings_rbac_and_tenancy(firm, make_client) -> None:
    cid, _ = await setup(firm)
    res = await post(firm.viewer, f"/companies/{cid}/meetings", MEETING)
    assert res.status_code == 403

    meeting = (await post(firm.executive, f"/companies/{cid}/meetings", MEETING)).json()
    rival = make_client()
    await register_firm(rival, "rival-meetings@example.com", "Rival")
    assert (await rival.get(f"/api/v1/companies/{cid}/meetings")).status_code == 404
    res = await post(rival, f"/meetings/{meeting['id']}/pack", {
        "letterhead": "none", "signatory_name": "X", "signatory_designation": "Y",
        "place": "Z",
    })
    assert res.status_code == 404
