# Firm Zero — the NYCA dogfood runbook

The PRD's own gate (§12): NYCA runs its real portfolio through Praxis before
any pilot invite. This is the step-by-step for that session, plus what the
simulated dogfood already verified and found.

## What the simulated dogfood proved (this repo, automated)

`scripts/seed_e2e.py` + `frontend/e2e/full-flow.spec.ts` run the ENTIRE
charter flow in a real Chromium against the live stack, in CI on every push:

register firm → invite a Manager → **Excel import** (3 companies, one with
no AGM date) → calendar generate from a TEST-ONLY ruleset → computed dates
correct to the day → **review queue** catches the turnover-gated rule
(applicability unknown) → reminder configuration on a row → **AGM Notice
generated** through a (test-)stamped template → the whole session visible in
the **activity log**.

Findings from getting it green (both fixed):
1. **CSRF bootstrap failed silently** — if `GET /auth/csrf` errored (e.g.
   rate-limited), the client cached `undefined` and every later mutation
   died with a misleading CSRF error. Now: loud failure with the real status,
   and concurrent bootstraps are deduped (two racing fetches could cache a
   token from a different response than the cookie).
2. **The RBAC matrix held up in the browser** — the invite form defaults to
   the Executive role; the flow then 403'd exactly where it should (an
   Executive editing an unassigned row's reminders). Not a bug — recorded
   because it is the matrix visibly working end-to-end.

## The real session (needs a human with the data — ~half a day)

Prerequisites: a deployed/staging instance (see RUNBOOK), and the partner's
laptop. NOTHING in this session requires code changes.

1. **Register** the firm (first user = Partner). Enable TOTP immediately
   (Partner-only, `/auth/totp/setup` via the UI when the settings screen
   gains the button — until then, via API).
2. **Team**: invite the actual staff with real roles. Watch the RBAC edges:
   executives should NOT see delete buttons succeed, the activity log, or
   the dead-letter view.
3. **Import the real portfolio**: export client master data to the template
   (or an MCA master-data file) and upload. EXPECT the all-or-nothing
   report to reject rows — that is the product working; fix and re-upload.
   Re-import is idempotent on CIN, so iterate freely.
4. **Record the facts the rules need**: per key company — AGM date, and the
   FY attributes screen (turnover band, GST registration, TAN, TP). This is
   what converts "confirm applicability" rows into real dates later.
5. **Rules**: the professional drafts the FIRST TEN real ROC rules in
   `backend/app/rules/dataset/roc.yaml` per docs/RULES_AUTHORING.md —
   AOC-4, MGT-7/7A, ADT-1, DIR-3 KYC, DPT-3, MSME-1 are the highest-value
   starters. `python -m app.rules.check` → PR → merge (= sign-off) →
   `python -m app.rules.load`.
6. **Generate calendars** for 5 representative companies across FY 2025-26
   and 2026-27. Work the review queue to zero for one company — time it.
   This number IS the onboarding metric (PRD target: whole firm < 4 hours).
7. **Reminders**: configure 30/15/7/1 on the nearest real deadline with the
   firm's SMTP settings; verify the email arrives and reads correctly.
8. **Templates**: the professional reviews + stamps AGM-NOTICE and
   LIST-DIRECTORS first (highest frequency); generate against a real
   company and read every line of the .docx.
9. **Registers**: seed the Register of Members for one company from the real
   cap table; amend an entry; check the history view and the as-on export.
10. **Log everything that felt wrong** — wording, ordering, missing fields —
    in a running list. Those observations, not new modules, set the next
    build priorities.

## Exit criteria (from the PRD, restated)

- One company's calendar fully resolved (no review flags) with every date
  traceable to a signed rule.
- One real reminder email received.
- Two stamped templates producing documents the professional would sign.
- Median per-company resolution time measured (target supports < 4h/firm).
