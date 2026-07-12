# M16 — Per-master import/export UI (M15's named follow-up)

Date: 12 July 2026
Frontend: tsc clean, 6 Vitest tests pass, build clean. E2E: **2/2 pass in a
real browser**, now including the new flow. Backend untouched.

## What shipped

The Directors and Shareholders tabs on the company detail page get the same
Excel controls the companies list has had since M3, wired to the M15 API:

- `useMasterIo(companyId, master)` in `CompanyDetail.tsx` — one hook renders
  the card-header actions (template download, export, hidden-file-input
  upload) and the report block for both masters.
- Same report contract as companies: green summary on success
  (`N created, M already present (skipped)` — the idempotent-skip count is
  now surfaced, `skipped` added to `ImportReport`), and on 422 the row-level
  all-or-nothing error list ("Nothing was imported — fix these rows").

## Browser-verified (full-flow E2E extended)

`seed_e2e.py` now also writes `frontend/e2e/fixtures/directors.xlsx`
(headers generated from the same shape as `MASTER_SPECS["directors"]`).
The full-flow spec opens Alpha Textiles, imports the file, asserts
`2 created`, then re-imports the identical file and asserts
`0 created, 2 already present` — idempotency demonstrated end to end.

## A real flake caught and pinned down

The first E2E run failed with the upload silently doing nothing: no request
ever reached the backend. Cause: `setInputFiles` resolved the file input
*during* the client-side navigation from the companies list to the detail
page — it grabbed the list page's (detaching) input, and the change event on
a detached node never reaches React's root listener. No error anywhere, the
upload just no-ops. Fix: assert the detail-page heading is visible before
touching the file input. Recorded as a spec-writing rule: **after a
navigation click, anchor on the destination page before locating elements
that also existed on the origin page.**

## NOT covered / follow-ups

- Dry-run toggle in the UI (API supports `?dry_run=true`; the list-page
  importer doesn't expose it either — do both together if wanted).
- Remaining named gaps from earlier ledgers: disclosures UI (M8), DSC-expiry
  reminders (M11), LLP calendar integration (M13), bulk calendar-row upload
  (M4).
