# M18 — DSC expiry reminders through the M5 pipeline

Date: 13 July 2026
Backend: **155 passed** (149 → 155, +6), ruff clean, mypy --strict clean,
dataset pre-flight OK. Frontend: tsc/Vitest/build clean. E2E: **2/2** in a
real browser, extended with the Partner-side policy roundtrip.

## The recipients decision (the thing that blocked this since M11)

DSC tokens have **no per-token owner** to fall back on: `holder_name` is free
text and linked directors have no login or email. So the recipients are a
**firm-level list**, set by a Partner alongside the reminder cadence —
`firm.settings["dsc_reminders"] = {days_before, recipients}`. A policy with
days but no recipients dead-letters with a clear reason (silent failure is a
defect, §4.6), exactly like a calendar reminder with no assignee.

## Design: generalize the dispatch, don't fork the pipeline

Rather than stand up a parallel reminder table (a "second datastore" smell,
charter §10), `reminder_dispatch` became **subject-polymorphic**:

- New `subject_kind` column (`'calendar_row'` default, `'dsc_token'`),
  nullable `reminder_config_id`, nullable `dsc_token_id` FK. Migration is
  additive and backward-compatible — existing rows are `calendar_row` via the
  server default; the calendar tests pass untouched.
- `deliver()` branches on `subject_kind`; the send + attempt-budget
  bookkeeping (1 try + 3 retries → dead) is now a shared `_send_and_record`
  used by both subjects, so retry/backoff/dead-letter behave identically.
- `schedule_dsc_reminders(session, today)` mirrors the calendar scheduler:
  for every DSC token with a **stored** future expiry, create idempotent
  queued dispatches at each `days_before` mark. No date is computed here —
  the expiry is master data, not a rules-engine output (C12).
- The daily worker cron now runs both schedulers; the queued→enqueue and
  manual-retry paths are subject-agnostic and needed no change.
- The dead-letter view and retry route already keyed on `firm_id`/`id`, so
  DSC failures appear there automatically — enriched with `subject_kind` and
  the holder name so a failure is identifiable.

## UI

Team & Settings gains a Partner-only "DSC expiry reminders" card
(days-before + recipient emails). The dead-letter table gains a Subject
column distinguishing DSC from calendar dispatches.

## Verified

- Integration (7 new): no-policy→nothing scheduled; idempotent + date-correct
  scheduling; already-expired tokens skipped; delivery to the firm recipient
  list with the right subject; no-recipients→dead-letter with holder label;
  policy PUT is Partner-only. Plus all 6 pre-existing calendar reminder tests
  still green (the refactor is behaviour-preserving).
- Browser: the partner sets `30, 7` / a recipient, reloads, and the policy
  round-trips through the API.

## NOT covered / follow-ups

- Disclosure reminders (chase outstanding MBP-1/DIR-8) could now reuse the
  same polymorphic dispatch — a natural M19 if wanted; needs its own subject
  kind and a cadence decision.
- Remaining ledger: bulk calendar-row Excel upload (M4), LLP calendar/rules
  integration (M13, schema-impacting).
