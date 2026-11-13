#!/usr/bin/env bash
# Runs once, when the PostgreSQL data volume is first initialised (docker-entrypoint-initdb.d).
# Creates the least-privileged runtime role used by the API. Row-Level Security always
# applies to it: no superuser, no BYPASSRLS, and it owns no tables.
set -euo pipefail

: "${SCHOOLTRACK_APP_DB_PASSWORD:?SCHOOLTRACK_APP_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v app_password="$SCHOOLTRACK_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE schooltrack_app
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'app_password';
SQL

echo "schooltrack: created runtime role schooltrack_app"
