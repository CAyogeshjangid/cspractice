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
