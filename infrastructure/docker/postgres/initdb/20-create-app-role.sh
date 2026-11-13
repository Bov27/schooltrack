#!/usr/bin/env bash
# Runs once, when the PostgreSQL data volume is first initialised (docker-entrypoint-initdb.d).
# Creates the non-owner roles used by the API (see ADR-002):
#   schooltrack_app       runtime role. Row-Level Security always applies: no superuser,
#                         no BYPASSRLS, owns no tables.
#   schooltrack_platform  Super-Admin operations across tenants (BYPASSRLS, not superuser),
#                         used only by platform endpoints and audited.
#   schooltrack_worker    Background worker (BYPASSRLS, not superuser) with grants limited
#                         to outbox processing and notifications (ADR-005).
set -euo pipefail

: "${SCHOOLTRACK_APP_DB_PASSWORD:?SCHOOLTRACK_APP_DB_PASSWORD must be set}"
: "${SCHOOLTRACK_PLATFORM_DB_PASSWORD:?SCHOOLTRACK_PLATFORM_DB_PASSWORD must be set}"
: "${SCHOOLTRACK_WORKER_DB_PASSWORD:?SCHOOLTRACK_WORKER_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v app_password="$SCHOOLTRACK_APP_DB_PASSWORD" \
     -v platform_password="$SCHOOLTRACK_PLATFORM_DB_PASSWORD" \
     -v worker_password="$SCHOOLTRACK_WORKER_DB_PASSWORD" <<'SQL'
CREATE ROLE schooltrack_app
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'app_password';
CREATE ROLE schooltrack_platform
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS
    PASSWORD :'platform_password';
CREATE ROLE schooltrack_worker
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS
    PASSWORD :'worker_password';
SQL

echo "schooltrack: created roles schooltrack_app, schooltrack_platform and schooltrack_worker"
