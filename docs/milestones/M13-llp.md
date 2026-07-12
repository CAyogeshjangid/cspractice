# M13 — LLP entity type (Phase 2)

Date: 12 July 2026
Backend suite: **146 passed** (142 → 146). Frontend TS-strict + build + Vitest clean.

## What was built (PRD §5, deliberately narrow: "LLP entity type with parallel
## masters and LLP Form 11/8 working papers — manual data, no MCA fetch")

- **LLP master** — LLPIN (unique per firm among non-deleted rows via partial
  index, same discipline as company CIN; a deleted LLPIN is reusable —
  tested), name, incorporation date, address, FY end, total contribution;
  soft delete Partner-only with reason.
- **Partners** — name, DPIN, designated flag, appointment/cessation dates,
  contribution, profit share. Working papers derive ACTIVE partner and
  designated-partner counts from this master server-side.
- **Form 11 / Form 8 working papers** — typed, FY-keyed (unique per
  llp+fy+form), draft → finalised lifecycle:
  - typed schema validation (422 listing missing/unknown fields, same
    philosophy as registers);
  - finalising REQUIRES the filing SRN (mirrors the calendar's
    filed-with-SRN rule);
  - finalised papers are read-only (409) — a filed return's working paper
    is a record, not a scratchpad.
- **No due dates anywhere in this module** — Form 11/8 deadlines belong to
  the rules dataset (C12). Filing on MCA stays manual by design (charter
  10.1).
- UI: LLPs page (list/add, partners, working-paper editor with derived
  counts and finalise flow). Migration `262fda290a37` applied on
  Postgres 16. RBAC + tenancy tested (rival firm can reuse an LLPIN).

## Decisions

1. **Separate `llp` table**, not an entity_type flag on company — the PRD
   calls LLPs a parallel data model, and company-specific flows (CIN
   validation, AGM anchors, registers) stay untouched and un-regressed.
2. LLP compliance-calendar integration is explicitly OUT of this milestone:
   `calendar_row` is company-keyed. When the professional wants LLP
   obligations (Form 11/8, DIR-3 KYC for DPs) on the calendar, the rules
   engine needs an entity-generalised subject — that is its own milestone
   with schema impact, not a rider.
3. Working-paper field schemas drafted in-house from the forms' data
   requirements; professional review refines them like everything else.

## NOT covered (honest gaps)

- LLP calendar/reminders (above), LLP document templates (LLP Agreement,
  partner resolutions — Phase 2 list §4.7 of the v1 doc), Register of
  Partners as a statutory register, Excel import for LLP portfolios.
- The working-company selector remains company-only; LLPs have their own
  page. Unifying the selector across entity types is UI work for when LLP
  usage justifies it.
