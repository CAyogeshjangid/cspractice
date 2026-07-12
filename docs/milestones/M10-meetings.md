# M10 — Meeting Scheduler (Phase 2)

Date: 11 July 2026
Backend suite: **136 passed** (131 → 136). Frontend TS-strict + build + Vitest clean.

## What was built (PRD §5: combined Notice/Minutes/Attendance packs per meeting per FY)

- **Meeting records**: BM / Committee / EGM / AGM per company per FY —
  date, time, venue, notice date, chairperson, agenda items, participant
  selection, draft/scheduled/held status. CRUD with FY and type filters,
  audit-logged, RBAC (Executive+ write, Viewer read), tenant-isolated.
- **Pack generation**: one call produces the meeting's full document set
  through the M6 stamped-template engine:
  - board/committee → BOARD-NOTICE + MEETING-MINUTES + ATTENDANCE-SHEET
  - agm/egm → AGM-NOTICE + MEETING-MINUTES + ATTENDANCE-SHEET
  All three land in the document library with snapshots; any unstamped
  template refuses the whole pack with the standard 422.
- **New template**: Board Meeting Notice (S.173 / SS-1), drafted in-house,
  ships unstamped like the rest.
- **Participant integrity**: attendance/minutes name ONLY the selected
  participants, resolved server-side from the directors register — a pack
  can never contain a name that isn't on the register (tested: the
  unselected director is absent from the generated attendance sheet).
  Implemented via a server-only `context_overrides` hook on the document
  service; the generic generation route cannot reach it, so the
  master-data-cannot-be-spoofed rule stands.
- **UI**: meetings page — FY-filtered list, schedule form with agenda lines
  and participant checkboxes from the register, pack dialog with letterhead
  + signatory, download links.
- Migration `9ed858c5e94d` applied on Postgres 16.

## Decisions

1. AGM/EGM notices show the MEETING's date (server-derived override), not
   the company master's AGM field — the notice describes this meeting.
2. Chairperson defaults to the first participant when unset.
3. Circular resolutions and CTC issuance (seen in the observed product) are
   NOT in scope — they need their own statutory treatment; raise as a
   product decision if firms ask.

## NOT covered (honest gaps)

- "Import agenda from Review Sheet" (v1-doc concept) — no Review Sheet
  module exists by design; agenda entry is manual.
- Minutes `conclusion_time` defaults to "—" in packs (fill after the
  meeting by regenerating minutes from the Documents page if needed).
- E2E smoke doesn't yet click through meetings — extend when the e2e seed
  script gains a stamped-template fixture.
