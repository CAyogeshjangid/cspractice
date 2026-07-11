"""M6 acceptance: AGM Notice renders with all merge fields resolved (opened
and asserted), unvalidated template → clear 422, library carries snapshots."""
from __future__ import annotations

import io

from docx import Document

from tests.conftest import post

COMPANY = {
    "cin": "U74999MH2020PTC555555",
    "name": "DocGen Fixture Pvt Ltd",
    "registered_address": "12 Marine Drive, Mumbai 400001",
    "agm_date": "2026-09-30",
}

AGM_PARAMS = {
    "meeting_time": "11:00 AM",
    "venue": "Registered Office, 12 Marine Drive, Mumbai 400001",
    "ordinary_business": [
        "To receive, consider and adopt the audited financial statements.",
        "To appoint the statutory auditor and fix their remuneration.",
    ],
    "special_business": [],
    "signatory_name": "R. Sharma",
    "signatory_designation": "Company Secretary",
    "place": "Mumbai",
}


async def setup_company(firm) -> str:
    import app.db as dbmod
    from app.services.documents import sync_templates

    async with dbmod._sessionmaker() as session:  # type: ignore[union-attr]
        await sync_templates(session)

    cid = (await post(firm.manager, "/companies", COMPANY)).json()["id"]
    await post(firm.manager, f"/companies/{cid}/directors", {
        "name": "A. Director", "din": "01234567", "designation": "Managing Director",
    })
    await post(firm.manager, f"/companies/{cid}/shareholders", {
        "name": "Holder One", "folio": "F001", "shares": 9000, "percentage": 90,
    })
    return cid


def docx_text(content: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(content)).paragraphs)


async def validate(firm, code: str):
    return await post(firm.manager, f"/templates/{code}/validate",
                      {"validated_by": "P. Professional", "membership_no": "F1234"},
                      method="PUT")


async def test_unvalidated_template_refused_with_clear_422(firm) -> None:
    cid = await setup_company(firm)
    res = await post(firm.manager, f"/companies/{cid}/documents",
                     {"template_code": "AGM-NOTICE", "letterhead": "company",
                      "params": AGM_PARAMS})
    assert res.status_code == 422
    assert "validation stamp" in res.json()["detail"]


async def test_agm_notice_all_merge_fields_resolve(firm) -> None:
    cid = await setup_company(firm)
    assert (await validate(firm, "AGM-NOTICE")).status_code == 200

    res = await post(firm.executive, f"/companies/{cid}/documents",
                     {"template_code": "AGM-NOTICE", "letterhead": "company",
                      "params": AGM_PARAMS})
    assert res.status_code == 201, res.text
    download = await firm.viewer.get(res.json()["download"])
    assert download.status_code == 200

    text = docx_text(download.content)
    assert "DocGen Fixture Pvt Ltd" in text
    assert "U74999MH2020PTC555555" in text
    assert "2026-09-30" in text
    assert "11:00 AM" in text
    assert "statutory auditor" in text
    assert "R. Sharma" in text
    assert "12 Marine Drive" in text  # company letterhead applied
    assert "{{" not in text and "{%" not in text  # every field resolved


async def test_missing_params_reported_not_blank(firm) -> None:
    cid = await setup_company(firm)
    await validate(firm, "AGM-NOTICE")
    res = await post(firm.manager, f"/companies/{cid}/documents",
                     {"template_code": "AGM-NOTICE", "params": {}})
    assert res.status_code == 422
    missing = res.json()["detail"]["missing"]
    assert "venue" in missing and "meeting_time" in missing


async def test_library_and_snapshot(firm) -> None:
    cid = await setup_company(firm)
    await validate(firm, "LIST-SHAREHOLDERS")
    res = await post(firm.manager, f"/companies/{cid}/documents",
                     {"template_code": "LIST-SHAREHOLDERS", "letterhead": "none",
                      "params": {"signatory_name": "R. Sharma",
                                 "signatory_designation": "CS", "place": "Mumbai"}})
    assert res.status_code == 201, res.text

    library = (await firm.viewer.get(f"/api/v1/companies/{cid}/documents")).json()
    assert len(library) == 1
    assert library[0]["template_code"] == "LIST-SHAREHOLDERS"
    assert library[0]["template_version"] == 1

    snapshot = (
        await firm.viewer.get(f"/api/v1/documents/{library[0]['id']}/snapshot")
    ).json()
    assert snapshot["context"]["shareholders"][0]["name"] == "Holder One"
    assert snapshot["context"]["total_shares"] == "9000"


async def test_all_six_templates_render(firm) -> None:
    """Every shipped template renders with a reasonable param set — golden
    smoke across the whole set (charter §8: golden test per template)."""
    cid = await setup_company(firm)
    common = {"signatory_name": "R. Sharma", "signatory_designation": "CS",
              "place": "Mumbai"}
    param_sets = {
        "AGM-NOTICE": AGM_PARAMS,
        "DIRECTORS-REPORT": {**common, "revenue": "1,00,00,000",
                             "profit_before_tax": "10,00,000",
                             "profit_after_tax": "7,50,000",
                             "state_of_affairs": "The company operated normally.",
                             "dividend": "Nil", "transfer_to_reserves": "Nil",
                             "board_meetings_held": "4",
                             "other_disclosures": "None."},
        "MEETING-MINUTES": {**common, "meeting_type": "Board Meeting",
                            "meeting_date": "2026-09-01", "meeting_time": "11:00 AM",
                            "venue": "Registered Office", "chairperson": "A. Director",
                            "agenda_items": ["Approval of accounts."],
                            "conclusion_time": "12:00 PM"},
        "ATTENDANCE-SHEET": {**common, "meeting_type": "Board Meeting",
                             "meeting_date": "2026-09-01", "venue": "Registered Office"},
        "LIST-DIRECTORS": common,
        "LIST-SHAREHOLDERS": common,
    }
    for code, params in param_sets.items():
        await validate(firm, code)
        res = await post(firm.manager, f"/companies/{cid}/documents",
                         {"template_code": code, "letterhead": "pcs", "params": params})
        assert res.status_code == 201, f"{code}: {res.text}"
        download = await firm.manager.get(res.json()["download"])
        text = docx_text(download.content)
        assert "{{" not in text and "{%" not in text, f"{code}: unresolved fields"
        assert "Test Firm" in text  # pcs letterhead = firm name


async def test_rbac_and_isolation(firm, make_client) -> None:
    cid = await setup_company(firm)
    # viewer cannot generate; executive cannot validate templates
    res = await post(firm.viewer, f"/companies/{cid}/documents",
                     {"template_code": "AGM-NOTICE"})
    assert res.status_code == 403
    res = await post(firm.executive, "/templates/AGM-NOTICE/validate",
                     {"validated_by": "X Y", "membership_no": "1"}, method="PUT")
    assert res.status_code == 403

    # cross-tenant: rival cannot see the library or download documents
    await validate(firm, "LIST-DIRECTORS")
    gen = await post(firm.manager, f"/companies/{cid}/documents",
                     {"template_code": "LIST-DIRECTORS",
                      "params": {"signatory_name": "R", "signatory_designation": "CS",
                                 "place": "Mumbai"}})
    doc_id = gen.json()["id"]

    from tests.conftest import register_firm

    rival = make_client()
    await register_firm(rival, "rival-docs@example.com", "Rival")
    assert (await rival.get(f"/api/v1/companies/{cid}/documents")).status_code == 404
    assert (await rival.get(f"/api/v1/documents/{doc_id}/download")).status_code == 404