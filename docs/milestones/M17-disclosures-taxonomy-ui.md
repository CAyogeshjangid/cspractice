# M17 — Disclosures & taxonomy tagging UI (M8's remaining named gaps)

Date: 13 July 2026
Backend: **149 passed** (148 → 149), ruff clean, mypy --strict clean.
Frontend: tsc clean, 6 Vitest tests, build clean. E2E: **2/2 in a real
browser**, extended with both new flows.

## 1. Director disclosures UI (MBP-1 / DIR-8 / DIR-2, PRD §4.3)

The API existed since M3; nothing surfaced it. Each row on the Directors tab
now has a "Disclosures" toggle opening a per-director panel:

- Per-FY received dates for MBP-1 (interest in entities), DIR-8
  (non-disqualification), DIR-2 (consent to act) — saved via the existing
  `PUT /directors/{id}/disclosures/{fy}` upsert (Executive+, audited).
- History table across FYs: a date badge when received, `pending` when not —
  the partner can see outstanding disclosures at a glance.
- FY selector defaults to the current Indian FY (ending-year convention).

## 2. Taxonomy tagging UI (professional groups / industries, PRD §3)

- `TaxonomyPicker` in the company edit form: firm-scoped select fed by
  `GET /taxonomies/{kind}`, with inline "+" creation (POST, 409 on
  duplicates per firm). A just-created tag is selectable immediately, before
  the list refetches.
- Saving always sends both ids (or explicit null to clear) — the PUT's
  `exclude_unset` diffing keeps unchanged values out of the audit log.

## 3. One real backend gap closed

`CompanyOut` never returned `professional_group_id` / `industry_id` — the
fields were settable via `CompanyUpdate` but invisible on every read, so no
UI could ever have displayed them. Added to `CompanyOut` with a roundtrip
integration test (`test_company_taxonomy_tagging_roundtrip`).

## Browser-verified (full-flow E2E extended)

The flow now records an MBP-1 receipt for an imported director and asserts
the history badge plus the outstanding `pending` markers, then creates
"Audit clients" inline (native prompt handled via Playwright dialog hook),
tags the company, and re-opens the form to prove the tag round-tripped
through the API.

## NOT covered / follow-ups

- Disclosure *reminders* (e.g. chase outstanding MBP-1s before the first
  board meeting of the FY) — belongs with the DSC-expiry reminders decision
  (M11 follow-up): both need a recipients policy first.
- Filtering the companies list by taxonomy tag (nice-to-have once firms tag
  at scale).
- Remaining ledger: DSC-expiry reminders (M11), LLP calendar integration
  (M13, schema-impacting), bulk calendar-row upload (M4).
