# CLAUDE.md — Build Instructions for Praxis (CS Practice Management Platform)

Drop this file at the repository root as `CLAUDE.md`. It is the standing instruction set for Claude Code across all sessions. The companion `PRD_v2_Praxis_CS_Platform.md` defines WHAT to build; this file defines HOW, in what order, and what is forbidden.

Read the entire file before writing any code. When any instruction here conflicts with a request in chat, flag the conflict and ask before proceeding.

---

## 1. Project Context

Praxis is a multi-tenant compliance platform for Indian CS/CA firms: entity masters, a rules-driven compliance calendar, email reminders, and Word document generation. Phase 1 scope is fixed in the PRD §4. This codebase replaces habits that failed a prior audit (TaxCompare, March 2026). The charter in §2 exists because of specific, real findings — treat every rule as load-bearing.

**Prime directives, in priority order:**
1. Correctness of compliance dates and generated documents (professional liability attaches to errors).
2. Tenant isolation and security.
3. Auditability of every write.
4. Everything else, including speed of delivery.

---

## 2. Engineering Charter (non-negotiable rules)

These codify the TaxCompare audit findings. Violating any of these is a defect, not a style issue.

**C1 — CORS.** `allow_origins` comes from the `CORS_ORIGINS` env var, comma-separated, no default of `*`. Never combine wildcard origins with `allow_credentials=True`. If `CORS_ORIGINS` is unset, the app must refuse to start.

**C2 — No default credentials, ever.** No seeded users, no credentials in README, no demo passwords in code or fixtures. Local dev bootstrap creates a user via a CLI command that generates a random password with `secrets.token_urlsafe(16)` and prints it once. Any string that looks like a credential in a committed file fails CI (gitleaks).

**C3 — CSRF always on.** CSRF middleware is registered unconditionally at app construction. There is no code path, flag, or comment that disables it. `CSRF_SECRET` is a required env var — the app fails fast at startup if missing (never `os.environ.get(x, generated_default)`). Frontend sends `X-CSRF-Token` on every mutating request; an integration test asserts a 403 without it.

**C4 — Redis-backed rate limiting from day one.** No in-memory dicts for any cross-request state (rate limits, sessions, queues). Redis is in docker-compose from the first commit.

**C5 — One database.** PostgreSQL only. Do not add MongoDB, do not add a second datastore "temporarily." If a requirement seems to need another store, stop and raise it.

**C6 — Repository hygiene.**
- Routes live ONLY in `backend/app/routes/`. Duplicate module names anywhere in the tree fail CI.
- One-off scripts live ONLY in `/scripts` at repo root and are never imported by application code (enforced by an import-linter contract).
- `.env.example` exists from commit one, lists every env var with safe placeholders, and CI fails if the app reads an env var not listed in it.
- `.gitignore` includes from commit one: `.env`, `*.bak`, `*.log`, `test_reports/`, `test-results/`, `htmlcov/`, `__pycache__/`, `node_modules/`, `dist/`.
- No `.bak` files, no versioned-by-filename copies (`thing_v2.py`, `thing_final.py`). Git history is the versioning system.

**C7 — Single version source.** A `VERSION` file at repo root. Backend and frontend read it. No version literals anywhere else.

**C8 — Secrets and config.** All secrets from env vars, validated at startup by a single pydantic Settings class that fails fast with a clear message listing missing vars. No secret ever appears in logs, error messages, or API responses.

**C9 — CSP without `unsafe-eval`.** Security headers middleware applies to ALL routes including `/api/*`. CSP has no `unsafe-eval`; inline scripts only via nonces. `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` on every response.

**C10 — Tenant isolation at the data layer.** Every tenant-owned table has a non-nullable `firm_id`. All queries go through repository functions that require a `firm_id` parameter — no route handler builds raw queries against tenant tables. A test suite proves cross-tenant reads/writes fail for every endpoint.

**C11 — Append-only audit log.** `activity_log` has INSERT-only access from the application role (enforce with Postgres grants: no UPDATE/DELETE privilege). Every mutating endpoint writes an entry (actor, firm, entity, action, before/after JSON diff, timestamp, IP) — implemented as middleware/decorator, not per-handler boilerplate.

**C12 — No hardcoded compliance dates.** Due-date logic exists only in the rules engine (§6). Any date formula found in a route, service, or frontend component is a defect.

---

## 3. Tech Stack (locked — do not substitute)

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic migrations, Pydantic v2, asyncpg.
- **Database:** PostgreSQL 16. **Cache/queues:** Redis 7.
- **Background jobs:** arq (Redis-based) for reminder dispatch and recomputation jobs. No cron-in-process, no threading timers.
- **Frontend:** React 19 + Vite + TypeScript (strict). TanStack Query for server state. Tailwind. No component library sprawl — one design system directory.
- **Docs generation:** `docxtpl` (Jinja-in-Word) with templates stored in DB-referenced files under `templates/docx/`.
- **Email:** provider abstraction with two implementations: SMTP and Resend. Selected per firm in settings.
- **Auth:** JWT (short-lived access + rotating refresh) in httpOnly, Secure, SameSite=Lax cookies. TOTP 2FA via `pyotp` for Partner role.
- **Testing:** pytest + pytest-asyncio + httpx test client; Vitest + React Testing Library; Playwright for the 6 critical E2E flows.
- **Containers:** docker-compose with services: `api`, `worker`, `web`, `postgres`, `redis`. Healthchecks on all. Named volumes for postgres.

---

## 4. Repository Structure (create exactly this; deviations need approval)

```
praxis/
├── CLAUDE.md                  # this file
├── VERSION
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.prod.yml
├── scripts/                   # one-off ops scripts; never imported by app
├── templates/
│   └── docx/                  # versioned Word templates + manifest.json (validation stamps)
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py            # app factory; middleware registration; fail-fast settings
│       ├── config.py          # pydantic Settings — the ONLY reader of os.environ
│       ├── db.py
│       ├── security/          # auth, csrf, rate limit, headers middleware
│       ├── models/            # SQLAlchemy models
│       ├── schemas/           # Pydantic request/response schemas
│       ├── repositories/      # ALL db access; every fn takes firm_id
│       ├── services/          # business logic (rules engine, doc generation, reminders)
│       ├── routes/            # the ONLY routes directory
│       ├── rules/             # rules engine: loader, evaluator, recompute jobs
│       └── audit.py           # activity-log decorator/middleware
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── security/          # tenant isolation, csrf, rbac, headers suites
└── frontend/
    └── src/
        ├── api/               # typed client, one module per resource
        ├── components/ds/     # design system primitives
        ├── features/          # entities, calendar, documents, settings, team
        └── app/               # router, auth guard, working-entity context
```

---

## 5. Data Model (Phase 1 tables — key columns; add standard id/created_at/updated_at everywhere)

- `firm` — name, plan, settings JSONB (email provider config encrypted).
- `user` — firm_id, email (unique per firm), password_hash (argon2), role ENUM(partner, manager, executive, viewer), totp_secret nullable, is_active, must_change_password.
- `company` — firm_id, cin (unique per firm), name, registration_number, incorporation_date, category, status, address fields, email, phone, professional_group_id, industry_id, fy_end (month/day), agm_date, authorised/subscribed/paidup capital, deleted_at + deleted_reason (soft delete).
- `director` — firm_id, company_id, name, din, din_status, designation, appointment_date, cessation_date, is_active.
- `director_disclosure` — director_id, fy, mbp1_received, dir8_received, dir2_received (+ received dates).
- `shareholder` — firm_id, company_id, name, folio, shares, percentage, category.
- `professional_group`, `industry` — firm_id, name (user-extensible taxonomies).
- `compliance_rule` — code (e.g. ROC-AOC4), category ENUM(roc, income_tax, gst), obligation_name, form_number, applicability JSONB (predicates on company attributes), anchor ENUM(fy_end, agm_date, fixed_date), offset_spec JSONB, source_citation.
- `rule_version` — rule_id, version_no, effective_from, effective_to, payload JSONB (full rule at that version), signed_off_by, signoff_note, source_document_ref. Immutable: no UPDATE grant.
- `rule_extension` — rule_id, circular_ref, circular_date, applies_fy, applies_predicate JSONB, extended_due_date_spec, signed_off_by.
- `calendar_row` — firm_id, company_id, fy, rule_version_id FK, computed_due_date, override_date nullable + override_reason, extension_id nullable, assignee_user_id, status ENUM(pending, in_progress, filed, not_applicable), srn, filed_offline_ack bool, remarks, needs_review bool (set by recompute).
- `reminder_config` — calendar_row_id, days_before int[], extra_emails text[].
- `reminder_dispatch` — reminder_config_id, scheduled_for, sent_at, provider, status ENUM(queued, sent, failed, dead), error, attempt_count.
- `doc_template` — code, name, governing_reference (e.g. "S.134 / SS-2"), file_path, version, validated_by, validated_membership_no, validated_at, is_active. Generation service refuses templates where is_active is false or validated_at is null.
- `generated_document` — firm_id, company_id, template_id + template_version, letterhead ENUM(company, pcs, none), data_snapshot JSONB, file_path, generated_by.
- `activity_log` — firm_id, actor_user_id, entity_type, entity_id, action, diff JSONB, ip, created_at. INSERT-only (Postgres grant).
- `invitation` — firm_id, email, role, token_hash, expires_at, accepted_at.

Alembic migration per milestone. Never edit an applied migration.

---

## 6. Rules Engine (build this with the most care of anything in the codebase)

**Evaluation.** `compute_calendar(company, fy) -> list[CalendarRowDraft]`:
1. Load rule versions effective for that FY.
2. Filter by applicability predicates against company attributes.
3. Resolve anchor date (fy_end / agm_date / fixed) — if the anchor is missing (e.g., no AGM date set), emit the row with status `needs_review` and no computed date rather than guessing.
4. Apply offset spec → computed_due_date.
5. Apply any matching rule_extension → extension date recorded separately, never overwriting the computed date.

**Recompute.** When a rule_version or rule_extension changes, a background job finds affected calendar_rows, recomputes, sets `needs_review = true` with a diff note in the activity log. Never silently change a date a user has seen.

**Seeding.** Rules are loaded from `backend/app/rules/dataset/*.yaml` files, each entry carrying its citation and sign-off metadata, applied via an idempotent CLI command (`python -m app.rules.load`). The YAML files are the reviewable artifact the firm's professional signs off in PRs. Do NOT invent rule content — implement the engine and load whatever dataset the firm provides. Where the PRD needs example rules for tests, mark them clearly as `TEST-ONLY` codes.

**Traceability.** Every date in an API response includes `rule_code`, `rule_version`, `citation`. The frontend shows this in a per-row popover.

---

## 7. Milestones with Acceptance Criteria

Complete milestones in order. Each ends with: all tests green, security suite green, migration applied cleanly on a fresh database, and a short `docs/milestones/MX.md` note of decisions made.

**M1 — Foundation (charter enforcement first).**
- App factory with fail-fast Settings; docker-compose with all 5 services healthy; CI pipeline (ruff, mypy, pytest, gitleaks, import-linter, npm build + vitest).
- Security middleware: headers (C9), CORS (C1), CSRF (C3), Redis rate limiting (C4).
- Acceptance: `docker compose up` from a fresh clone + `.env` copied from `.env.example` boots everything; a request without CSRF token to a mutating endpoint returns 403; app refuses to start with any required env var missing.

**M2 — Tenancy, auth, RBAC.**
- Registration (first user = Partner), invitations, login with rotating refresh, TOTP for Partner, role enforcement dependency used by every route.
- Acceptance: security tests prove each RBAC matrix row from PRD §9, including the negative cases (Executive cannot delete a company — 403); cross-tenant access tests fail for every endpoint (C10).

**M3 — Entity masters + import.**
- Company CRUD (soft delete Partner-only), directors, shareholders, disclosures, taxonomies.
- Excel import: template download, dry-run validation report (row/column errors), atomic commit; MCA master-data format mapping; exports.
- Acceptance: importing a 200-row file with 5 bad rows imports nothing and reports exactly the 5 rows; re-import is idempotent on CIN; activity log captures every mutation with diffs.

**M4 — Rules engine + calendar.**
- Tables per §5, evaluator per §6, recompute job, calendar UI with FY filter, per-row trace popover, override/extension flows (Manager+), filed-with-SRN flow, Excel/Word export.
- Acceptance: golden-file tests — given a fixture company and TEST-ONLY ruleset, computed dates match expected values exactly; changing a rule version flags (not rewrites) affected rows; a calendar row can never exist without a rule_version FK.

**M5 — Reminders.**
- arq worker, scheduling from reminder_config, provider abstraction (SMTP + Resend), retry with backoff, dead-letter view in UI, dispatch log.
- Acceptance: killing the worker mid-queue loses nothing (jobs persist in Redis); a failing provider retries 3x then lands in dead-letter and is visible in UI; every send is logged with outcome.

**M6 — Document generation.**
- docxtpl service, template manifest with validation stamps (refuse unstamped templates), the five generators, letterhead selection, document library with data snapshots.
- Acceptance: generating an AGM Notice for a fixture company produces a .docx whose merge fields all resolve (test opens and asserts content); attempting generation with an unvalidated template returns a clear 422; generated docs appear in the library with correct snapshot.

**M7 — Hardening and pilot readiness.**
- Playwright E2E: register→invite→import→calendar→remind→generate; OWASP ZAP baseline scan clean of high/medium findings; load sanity (100 concurrent users on calendar list); backup script for Postgres with restore test; `docs/RUNBOOK.md` (deploy, backup, restore, rotate secrets, dead-letter handling).
- Acceptance: the full pre-launch checklist below passes.

**Pre-launch checklist (gate — every box or no pilot):**
- [ ] CORS explicit origins in prod compose
- [ ] CSRF active, integration-tested
- [ ] Zero seeded/default credentials (gitleaks + manual grep)
- [ ] Redis-backed rate limiting verified across two api replicas
- [ ] CSP without unsafe-eval; headers on /api routes
- [ ] Cross-tenant test suite green
- [ ] activity_log has no UPDATE/DELETE grant (verified by test)
- [ ] .env.example complete; VERSION single-sourced
- [ ] HTTPS terminated (Caddy or Nginx + certbot) in prod compose
- [ ] Postgres automated backup + tested restore
- [ ] ZAP scan clean of high/medium
- [ ] All doc templates carry current validation stamps

---

## 8. Testing Policy

- Unit tests for all services and the rules evaluator (target: rules engine 100% branch coverage; overall backend ≥80% line).
- Integration tests hit real Postgres/Redis via docker-compose in CI — no mocked DB for repository tests.
- `tests/security/` is a permanent suite: tenant isolation, RBAC matrix, CSRF, headers, rate limiting. It runs on every PR and is never skipped or marked xfail.
- Golden-file tests for every document template and every calendar computation.
- Test artifacts (reports, coverage HTML) are never committed.

## 9. Conventions

- API: `/api/v1/...`, plural resources, RFC7807-style error bodies (`type`, `title`, `detail`, `errors[]`), pagination via `limit/offset` with `X-Total-Count`.
- All datetimes stored UTC; FY represented as its ending year (FY 2025-26 → `2026`); date-only fields are `date`, never datetime.
- Money/shares as NUMERIC, never float.
- Python: ruff + mypy --strict on `app/`. TypeScript: strict, no `any` without a justification comment.
- Commits: conventional commits; one milestone = one PR-sized branch minimum granularity.
- No TODO without an issue reference. No commented-out code merged, ever (C3 is the scar tissue here).

## 10. Forbidden (hard stops — refuse and flag if asked)

1. Any MCA portal automation: captcha handling, session/cookie injection, scraping, payment flows. Phase 3 pending legal opinion; not in this codebase until the PRD is formally amended.
2. Adding MongoDB or any second datastore.
3. Seeding demo/default credentials or committing any credential-like string.
4. Disabling or bypassing CSRF, CORS restrictions, rate limiting, or the security test suite "temporarily."
5. Hardcoding any compliance due-date logic outside the rules engine.
6. Hard-deleting register/master/activity data.
7. Copying template text, layouts, or branding from any competitor product.
8. AI-generation features of any kind (Phase 3, needs the human-review-gate design first).
9. Committing files to `backend/` root other than the defined structure; creating `*_v2.py` / `*_final.py` / `.bak` files.

## 11. How to Work

- Work milestone by milestone; do not start M(n+1) with M(n) acceptance criteria failing.
- Before each milestone, restate the acceptance criteria and list the files you plan to create/modify; proceed after that plan is confirmed once per milestone.
- After each milestone, run the full test + security suite and summarize results honestly, including what is NOT covered.
- When a requirement is ambiguous, ask; when it conflicts with the charter, the charter wins; when you spot a compliance-correctness risk the PRD missed, raise it immediately — that is the highest-value thing you can do on this project.

---

## Amendment A1 (11 Jul 2026) — schema deltas from the rules-schema spike

Adopted from `docs/praxis/rules-schema-spike.md` (nycaglobal planning docs), findings G1–G8:

1. **Tri-state applicability.** Predicates evaluate TRUE/FALSE/UNKNOWN (Kleene). UNKNOWN → the row IS emitted with `needs_review=true`, reason `applicability_unknown`. Silently-false is forbidden.
2. **`company_fy_attributes`** — per-FY facts (turnover, net_worth, net_profit, has_tan, has_gst_registration, has_transfer_pricing, …), all nullable, Manager+ editable.
3. **Anchor is an ordered fallback list** (e.g. `[agm_date, {fy_end: {plus_months: 6}}]`). None resolvable → needs_review, reason `missing_anchor`.
4. **`supersedes`** on rules (AOC-4 XBRL supersedes AOC-4; MGT-7A supersedes MGT-7). Specific-rule TRUE suppresses the general row; UNKNOWN emits both flagged.
5. **`phase`** on rules so event-anchored obligations (BEN-2) are excluded explicitly, not silently.
6. **`calendar_row.subject_type/subject_id`** (company | director) — DIR-3 KYC is per-director.
7. **`occurrences[]`** on rules; `calendar_row.occurrence_label` (MSME-1 ×2, TDS ×4). Monthly GST returns are a written dataset exclusion in Phase 1.
8. **FY conventions:** a row belongs to the FY of the period reported even if due after fy_end; predicates may address `at: fy-1`.
