# Praxis Runbook

Operational procedures (charter M7). Assumes the prod compose stack:
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.

## Deploy

1. `git pull` on the host; review the diff of migrations since last deploy.
2. `docker compose build api worker web`
3. `docker compose run --rm api alembic upgrade head` — migrations are
   forward-only; never edit an applied migration.
4. `docker compose up -d` (rolling: api has 2 replicas behind Caddy).
5. Post-deploy checks: `GET /api/v1/health` returns the new VERSION; a
   mutating request without `X-CSRF-Token` returns 403.

First deploy only: create the runtime DB role and set `PRAXIS_DOMAIN`:
```sql
CREATE ROLE praxis_app LOGIN PASSWORD '<generated>';
-- re-run: alembic upgrade head applies the grant block once the role exists
```
Then load the signed rules dataset and template registry:
```
docker compose run --rm api python -m app.rules.load
docker compose run --rm api python -m app.services.documents
```
Templates must then be stamped by the reviewing professional via
`PUT /api/v1/templates/{code}/validate` before any generation works —
this is deliberate (PRD §4.7).

## Backup / restore

- Nightly cron on the host:
  `DATABASE_URL_PG=postgres://praxis:***@localhost:5432/praxis scripts/backup.sh /backups`
  The script verifies every dump with `pg_restore --list` and keeps 30.
- **Test the restore monthly** (checklist requirement):
  `DATABASE_URL_PG=postgres://praxis:***@localhost:5432/postgres scripts/restore.sh /backups/<dump> praxis_verify`
  then `DROP DATABASE praxis_verify`. The script refuses to overwrite an
  existing database by design.
- Generated documents live in the `docstore` volume — include it in host
  filesystem backups (documents are re-generatable from snapshots, but SRN
  history is not).

## Rotate secrets

1. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. `JWT_SECRET` rotation invalidates all sessions AND the encryption of
   stored provider secrets (Fernet key is derived from it): re-enter firm
   email settings after rotating, or rotate during a maintenance window.
3. `CSRF_SECRET` rotation is safe anytime (clients re-fetch `/auth/csrf`).
4. Update `.env`, then `docker compose up -d` (api + worker restart).

## Reminder dead-letter handling

- Managers see failures at `GET /api/v1/reminders/dead-letter`.
- Typical causes: provider misconfiguration (fix in firm email settings,
  then `POST /api/v1/reminders/{id}/retry`), or "no recipients" (assign the
  calendar row or add extra_emails, then retry).
- The worker's daily sweep (01:30 UTC) re-enqueues anything left `queued`.
- Worker down? `docker compose logs worker`. Jobs persist in Redis; a
  restart resumes the queue. Nothing is lost by restarting the worker.

## Rules dataset updates (the 48-hour circular drill, PRD §7)

1. Editor drafts the change in `backend/app/rules/dataset/*.yaml` on a
   branch, citing the circular; the named professional reviews and the PR
   merge records the sign-off.
2. Deploy, then `docker compose run --rm api python -m app.rules.load` —
   affected calendar rows are flagged `rule_revised` automatically; dates
   change only on regenerate, and stay flagged until acknowledged.
3. Firms see flagged rows in their review queue (`needs_review=true` filter).

## Incident: suspected cross-tenant access

1. Preserve `activity_log` (it is INSERT-only at the DB layer).
2. Query by firm_id/actor to establish scope; the log carries IPs and diffs.
3. Rotate JWT_SECRET (kills all sessions), disable affected users
   (`is_active=false`), then investigate before re-enabling.
4. DPDP breach-notification obligations may apply — escalate to the Partner
   and counsel; see PRD §10.
