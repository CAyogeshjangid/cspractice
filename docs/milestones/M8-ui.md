# M8 — Frontend build-out + browser E2E

Date: 11 July 2026
Backend suite: **115 passed** (111 → 115, new team-members endpoint + RBAC
tests). Frontend: TS-strict clean, production build clean.
**Playwright E2E: 1 passed in real Chromium** against the full live stack
(vite → FastAPI → Postgres + Redis).

## What was built

- **App shell** (charter §4 frontend structure): sidebar navigation, auth
  guard, and the persistent **working-company selector** (PRD §3 — a UI
  convenience only; authorization stays server-side per request).
- **Auth**: register-first-Partner, login with the TOTP step-up flow
  (`totp_required` → code field), invitation-accept page (`/accept?token=`).
- **Companies**: list, inline add, **Excel import with the all-or-nothing
  row-level error report rendered in place**, template download, export.
- **Company detail**: directors (add/list), cap table with the percentage
  warning, and the **per-FY facts editor** feeding the rules engine's
  tri-state predicates (explains the "confirm applicability" behavior).
- **Compliance calendar** (the core screen): FY filter, generate/refresh,
  **review-queue toggle with count**, flagged-row highlighting with reasons,
  **per-row trace popover** (rule code → version → citation → computed/
  extension/override dates, PRD §7), row editor covering status,
  filed-with-SRN / filed-offline, assignee (team roster), override with
  reason, acknowledge-review, and **reminder configuration**; Excel + Word
  export links.
- **Documents**: template registry with stamp state, **stamping form**
  (name + membership number), generator with per-template parameter forms
  and letterhead selection, library with downloads.
- **Team & Settings**: roster, Partner-only invitations (one-time link
  surfaced with a copy hint), Manager+ **dead-letter view with retry**,
  Partner-only email provider settings (secrets write-only, presence flags).
  Role-gated sections self-hide on 403 — cosmetic only; the server enforces.
- **New endpoint**: `GET /api/v1/team/members` (any authenticated role) for
  assignee pickers, with RBAC tests.

## E2E

`frontend/e2e/smoke.spec.ts` — register → add company → working-company
selection → calendar generate (honest empty state without a signed dataset)
→ template registry. Runs headless Chromium; config honors
`PLAYWRIGHT_CHROMIUM_PATH` for preinstalled browsers.

## NOT covered (honest gaps)

- E2E does not yet cover import→calendar-rows→remind→generate (needs a
  TEST-ONLY dataset loaded in the e2e environment — wire into a staging
  seed script); Vitest component tests not yet written.
- E2E is not in CI yet (needs Postgres/Redis + built frontend orchestration
  in the workflow — add a job when CI minutes matter less than coverage).
- No taxonomy tagging UI, disclosure (MBP-1/DIR-8/DIR-2) UI, or company
  edit/soft-delete UI yet — API-complete, screens pending.
- Assignee column shows "assigned"; showing the member email needs a join
  or client-side roster lookup — trivial follow-up.
