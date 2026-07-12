# M11 — Practice masters: Auditors, PCS, DSC tracker (Phase 2)

Date: 11 July 2026
Backend suite: **140 passed** (136 → 140). Frontend TS-strict + build + Vitest clean.

## What was built (PRD §5: "Charges, Auditors master, PCS master, DSC token tracker")

- **Auditor master** — CA firms with FRN (unique per firm; a rival firm can
  reuse the same FRN — tested), reusable across engagements.
- **Auditor appointments** — per company: from-FY / to-FY (open-ended =
  current auditor), ADT-1 SRN, joined listing with the auditor's name.
- **PCS master** — practicing CS professionals (membership no. unique per
  firm, COP no., firm) for signing blocks and letterheads.
- **DSC token tracker** — holder, optional director link, token colour/
  number, expiry, remarks; listed by expiry with an "expiring soon" badge
  computed in the UI (expiry math deliberately stays out of routes — C12
  discipline even for non-statutory dates).
- All endpoints audited, RBAC-gated (Executive+ write, Viewer read),
  tenant-isolated (tested). UI: one Practice Masters page with the three
  sections. Migration `2688c17513df` applied on Postgres 16.

## Decision: Charges intentionally has NO separate table

The §85 **Register of Charges** shipped in M9 (append-only, typed fields:
holder, amount, creation/modification/satisfaction dates, property
description, charge id) IS the charges feature. A parallel mutable "charges
master" would create two sources of truth for a legal record — the exact
failure mode the §8 architecture exists to prevent. If an operational
charges view is wanted later (e.g. satisfaction-due dashboards), build it
as a READ view over the register.

## NOT covered (honest gaps)

- PCS/auditor records don't yet feed document letterhead/signing blocks
  automatically (documents still use firm.name for PCS letterhead) — wire
  a default-PCS selection into `documents.build_context` when the
  professional confirms the desired block format.
- DSC expiry reminders via the M5 pipeline (a "DSC expiring" email) —
  natural follow-up; needs a product decision on recipients.
- Excel import/export for these masters — reuse the import service when a
  pilot firm brings real lists.
