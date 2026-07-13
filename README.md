# Praxis — CS Practice Management Platform

Multi-tenant compliance platform for Indian CS/CA firms: entity masters, a
rules-driven compliance calendar with professional sign-off traceability,
email reminders, and Word document generation.

- **What to build:** `docs/PRD_v2.md`
- **How to build it (engineering charter):** `CLAUDE.md` — non-negotiable
  security/quality rules born from a prior audit; read before contributing.
- **Planning artifacts:** `docs/planning/` (PRD review, rules-schema spike)
- **Rules dataset authoring:** `docs/RULES_AUTHORING.md` — the guide for the
  professional who signs the dataset; `python -m app.rules.check` pre-flights
  every dataset PR in CI
- **Milestone log:** `docs/milestones/`

## Status

| Milestone | State |
|---|---|
| M1 Foundation (security middleware, rules engine core, migrations) | ✅ |
| M2 Tenancy, auth, RBAC (invitations, rotating refresh, TOTP) | ✅ |
| M3 Entity masters + Excel import | ✅ |
| M4 Rules persistence + compliance calendar | ✅ |
| M5 Reminders (arq worker, SMTP/Resend, dead-letter) | ✅ |
| M6 Document generation (docxtpl, validation stamps, library) | ✅ |
| M7 Hardening (backup/restore, prod compose, runbook, prelaunch tests) | ✅ code-complete — staging ZAP pending |
| M8 Frontend (shell, calendar UI, documents, team) + Chromium E2E | ✅ |
| M9 Phase 2: Statutory Registers (14 registers, append-only §8) | ✅ |
| M10 Phase 2: Meeting Scheduler (Notice/Minutes/Attendance packs) | ✅ |
| M11 Phase 2: Practice masters (Auditors, PCS, DSC tracker) | ✅ |
| M12 Phase 2: Annual Filing Suite (Shorter Notice, Auditor Appt, MR-3) | ✅ |
| M13 Phase 2: LLP entity type (masters, partners, Form 11/8 papers) | ✅ |
| M14 Dogfood: full-flow browser E2E, firm-zero runbook | ✅ |
| M15 Debt closure: masters Excel import/export, mypy --strict | ✅ |
| M16 Per-master import/export UI on company detail (+E2E) | ✅ |
| M17 Disclosures (MBP-1/DIR-8/DIR-2) + taxonomy tagging UI | ✅ |

## Development

```bash
cp .env.example .env       # fill in secrets (the app refuses placeholders)
docker compose up          # api, worker, web, postgres, redis
```

Backend tests (need Postgres 16 + Redis 7 reachable via env vars):

```bash
cd backend
pip install -e '.[dev]'
alembic upgrade head
pytest
```

This repository was extracted from the `nycaglobal` planning repo with full
history (`git subtree split`). Rules dataset YAML files are the reviewable
artifact a named professional signs off in PRs — unsigned rules never load
outside tests.
