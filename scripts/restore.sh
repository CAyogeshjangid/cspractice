#!/usr/bin/env bash
# Restore a backup into a FRESH database (charter M7: restore must be tested,
# not assumed). Refuses to restore over an existing non-empty database.
# Usage: DATABASE_URL_PG=postgres://user:pass@host:5432/postgres \
#        ./scripts/restore.sh <dump-file> <new-db-name>
set -euo pipefail

DUMP="${1:?usage: restore.sh <dump-file> <new-db-name>}"
NEWDB="${2:?usage: restore.sh <dump-file> <new-db-name>}"
: "${DATABASE_URL_PG:?set DATABASE_URL_PG (postgres:// DSN to the postgres db)}"

pg_restore --list "$DUMP" > /dev/null || { echo "dump unreadable: $DUMP"; exit 1; }

EXISTS=$(psql "$DATABASE_URL_PG" -tAc "SELECT 1 FROM pg_database WHERE datname='$NEWDB'")
if [ "$EXISTS" = "1" ]; then
  echo "refusing: database $NEWDB already exists (restore only into fresh databases)"
  exit 1
fi

psql "$DATABASE_URL_PG" -c "CREATE DATABASE \"$NEWDB\""
pg_restore --no-owner --dbname="${DATABASE_URL_PG%/*}/$NEWDB" "$DUMP"

TABLES=$(psql "${DATABASE_URL_PG%/*}/$NEWDB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
echo "restored $DUMP into $NEWDB ($TABLES tables)"
