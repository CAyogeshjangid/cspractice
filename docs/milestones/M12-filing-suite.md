# M12 — Annual Filing Suite expansion (Phase 2)

Date: 12 July 2026
Backend suite: **142 passed** (140 → 142). Frontend TS-strict + build clean.

## What was built (PRD §5: Shorter Notice, Board Meeting Attendance, Auditor Appointment, MR-3 skeleton)

Three new in-house templates (statute-skeleton wording, shipped unstamped
like all others; production use requires the professional's stamp):

- **SHORTER-NOTICE** — member's consent to shorter notice (proviso to
  S.101(1) / SS-2), member/folio/shares as parameters.
- **AUDITOR-APPOINTMENT** — intimation of appointment under S.139 with the
  S.141 eligibility-confirmation request and the ADT-1 filing note.
  **Integration:** the letter auto-fills the auditor's name, FRN, and
  address from the company's CURRENT M11 appointment (open-ended
  engagement) — server-derived, so the letter can only name the auditor on
  record. With no appointment recorded, generation returns the standard
  422 listing `auditor_name` etc. (tested both ways).
- **MR-3** — Secretarial Audit Report skeleton (S.204 / Form MR-3): scope
  paragraph, the statutory checklist headings, observations placeholder,
  PCS signing block with membership/COP numbers.

Decision: **no separate "Board Meeting Attendance" template** — the
existing ATTENDANCE-SHEET is meeting-type-parameterised and already serves
board meetings (used by M10 packs); a duplicate would fork maintenance.

## Bug found and fixed by the new tests

**docx XML escaping:** a literal `&` in a name ("S. Auditors & Co.")
was silently dropped from rendered documents — raw ampersands are invalid
in the docx XML body. Rendering now uses Jinja `autoescape=True` (correct
for XML output), preserving `&`, `<`, `>` in company/auditor names across
ALL templates. A silent character drop in a statutory document is exactly
the class of defect the golden tests exist to catch.

## NOT covered (honest gaps)

- Template catalog now stands at 10 codes; all still bare skeletons pending
  the professional's layout + stamping pass.
- MR-3's statutory checklist is the fixed skeleton; listed-company
  SEBI-regulation items should be refined during professional review.
- Shorter-notice consent is per-member; a bulk "generate for all members"
  helper is a small follow-up if firms want it.
