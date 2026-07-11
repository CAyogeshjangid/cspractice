"""One-off: build the Phase 1 .docx template skeletons (charter C6: lives in
/scripts, never imported by app code).

Content is drafted in-house from the bare statutory skeleton (Companies Act
2013 / Secretarial Standards headings) — no competitor text, layouts, or
branding (charter 10.7). Templates ship UNSTAMPED: manifest.json carries
validated_* as null and generation refuses them until a professional stamps
each via the API (PRD §4.7).

Run from repo root:  python scripts/build_templates.py
"""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document

OUT = Path(__file__).resolve().parents[1] / "templates" / "docx"

LETTERHEAD_BLOCK = [
    "{% if letterhead_name %}{{ letterhead_name }}{% endif %}",
    "{% if letterhead_address %}{{ letterhead_address }}{% endif %}",
]

SIGNING_BLOCK = [
    "",
    "By order of the Board",
    "For {{ company_name }}",
    "",
    "_______________________",
    "{{ signatory_name }}",
    "{{ signatory_designation }}",
    "Date: {{ document_date }}",
    "Place: {{ place }}",
]


def build(filename: str, title: str, body: list[str]) -> None:
    doc = Document()
    for line in LETTERHEAD_BLOCK:
        doc.add_paragraph(line)
    heading = doc.add_heading(title, level=1)
    heading.alignment = 1  # centered
    for line in body:
        doc.add_paragraph(line)
    OUT.mkdir(parents=True, exist_ok=True)
    doc.save(OUT / filename)
    print(f"built {filename}")


build(
    "agm_notice.docx",
    "NOTICE OF ANNUAL GENERAL MEETING",
    [
        "NOTICE is hereby given that the Annual General Meeting of "
        "{{ company_name }} (CIN: {{ cin }}) will be held on {{ agm_date }} "
        "at {{ meeting_time }} at {{ venue }} to transact the following business:",
        "",
        "ORDINARY BUSINESS:",
        "{% for item in ordinary_business %}",
        "{{ loop.index }}. {{ item }}",
        "{% endfor %}",
        "{% if special_business %}",
        "SPECIAL BUSINESS:",
        "{% for item in special_business %}",
        "{{ loop.index }}. {{ item }}",
        "{% endfor %}",
        "{% endif %}",
        *SIGNING_BLOCK,
        "",
        "Notes: A member entitled to attend and vote is entitled to appoint a "
        "proxy to attend and vote instead of the member.",
    ],
)

build(
    "directors_report.docx",
    "BOARD'S REPORT",
    [
        "To the Members of {{ company_name }},",
        "Your Directors present their report together with the audited financial "
        "statements for the financial year ended {{ fy_end_date }}.",
        "",
        "1. FINANCIAL RESULTS (₹)",
        "Revenue from operations: {{ revenue }}",
        "Profit/(Loss) before tax: {{ profit_before_tax }}",
        "Profit/(Loss) after tax: {{ profit_after_tax }}",
        "",
        "2. STATE OF THE COMPANY'S AFFAIRS",
        "{{ state_of_affairs }}",
        "",
        "3. DIVIDEND",
        "{{ dividend }}",
        "",
        "4. TRANSFER TO RESERVES",
        "{{ transfer_to_reserves }}",
        "",
        "5. DIRECTORS AND KEY MANAGERIAL PERSONNEL",
        "{% for d in directors %}",
        "{{ d.name }} ({{ d.din }}) — {{ d.designation }}",
        "{% endfor %}",
        "",
        "6. NUMBER OF BOARD MEETINGS",
        "{{ board_meetings_held }}",
        "",
        "7. DIRECTORS' RESPONSIBILITY STATEMENT",
        "Pursuant to Section 134(5) of the Companies Act, 2013, the Board of "
        "Directors, to the best of their knowledge and ability, confirm the "
        "matters stated therein.",
        "",
        "8. DECLARATIONS AND DISCLOSURES",
        "{{ other_disclosures }}",
        *SIGNING_BLOCK,
    ],
)

build(
    "meeting_minutes.docx",
    "MINUTES OF THE MEETING",
    [
        "Minutes of the {{ meeting_type }} of {{ company_name }} "
        "(CIN: {{ cin }}) held on {{ meeting_date }} at {{ meeting_time }} "
        "at {{ venue }}.",
        "",
        "PRESENT:",
        "{% for d in directors %}",
        "{{ d.name }} — {{ d.designation }}",
        "{% endfor %}",
        "",
        "CHAIRPERSON: {{ chairperson }}",
        "",
        "PROCEEDINGS:",
        "{% for item in agenda_items %}",
        "{{ loop.index }}. {{ item }}",
        "{% endfor %}",
        "",
        "There being no other business, the meeting concluded at "
        "{{ conclusion_time }} with a vote of thanks to the Chair.",
        *SIGNING_BLOCK,
    ],
)

build(
    "attendance_sheet.docx",
    "ATTENDANCE SHEET",
    [
        "{{ meeting_type }} of {{ company_name }} (CIN: {{ cin }}) held on "
        "{{ meeting_date }} at {{ venue }}.",
        "",
        "ATTENDEES:",
        "{% for d in directors %}",
        "{{ loop.index }}. {{ d.name }} — {{ d.designation }} — DIN: {{ d.din }} — Signature: ______________",
        "{% endfor %}",
        *SIGNING_BLOCK,
    ],
)

build(
    "list_of_directors.docx",
    "LIST OF DIRECTORS",
    [
        "{{ company_name }} (CIN: {{ cin }}) — as on {{ document_date }}",
        "",
        "{% for d in directors %}",
        "{{ loop.index }}. {{ d.name }} — DIN: {{ d.din }} — {{ d.designation }} — "
        "Appointed: {{ d.appointment_date }}",
        "{% endfor %}",
        *SIGNING_BLOCK,
    ],
)

build(
    "list_of_shareholders.docx",
    "LIST OF SHAREHOLDERS",
    [
        "{{ company_name }} (CIN: {{ cin }}) — as on {{ document_date }}",
        "",
        "{% for s in shareholders %}",
        "{{ loop.index }}. {{ s.name }} — Folio: {{ s.folio }} — Shares: {{ s.shares }} "
        "({{ s.percentage }}%) — {{ s.category }}",
        "{% endfor %}",
        "",
        "Total shares: {{ total_shares }}",
        *SIGNING_BLOCK,
    ],
)

manifest = [
    {"code": "AGM-NOTICE", "name": "AGM Notice", "governing_reference": "S.101 / SS-2",
     "file": "agm_notice.docx", "version": 1},
    {"code": "DIRECTORS-REPORT", "name": "Directors' Report (skeleton)",
     "governing_reference": "S.134", "file": "directors_report.docx", "version": 1},
    {"code": "MEETING-MINUTES", "name": "Board/AGM Meeting Minutes",
     "governing_reference": "S.118 / SS-1, SS-2", "file": "meeting_minutes.docx", "version": 1},
    {"code": "ATTENDANCE-SHEET", "name": "Attendance Sheet",
     "governing_reference": "SS-1 / SS-2", "file": "attendance_sheet.docx", "version": 1},
    {"code": "LIST-DIRECTORS", "name": "List of Directors",
     "governing_reference": "S.170", "file": "list_of_directors.docx", "version": 1},
    {"code": "LIST-SHAREHOLDERS", "name": "List of Shareholders",
     "governing_reference": "S.88", "file": "list_of_shareholders.docx", "version": 1},
]
# validation stamps deliberately absent: templates are unusable until a named
# professional stamps them via PUT /api/v1/templates/{code}/validate
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("built manifest.json (unstamped)")
