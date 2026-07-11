#!/usr/bin/env bash
# Postgres backup (charter M7). Run from cron on the host or a sidecar.
# Usage: DATABASE_URL_PG=postgres://user:pass@host:5432/praxis ./scripts/backup.sh /backups
set -euo pipefail

DEST="${1:?usage: backup.sh <dest-dir>}"
: "${DATABASE_URL_PG:?set DATABASE_URL_PG (postgres:// DSN, no +asyncpg)}"

mkdir -p "$DEST"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/praxis-$STAMP.dump"

pg_dump --format=custom --no-owner --dbname="$DATABASE_URL_PG" --file="$OUT"
# integrity check: a dump we cannot list is not a backup
pg_restore --list "$OUT" > /dev/null
echo "backup written and verified: $OUT ($(du -h "$OUT" | cut -f1))"

# retention: keep the newest 30
ls -1t "$DEST"/praxis-*.dump 2>/dev/null | tail -n +31 | xargs -r rm --
