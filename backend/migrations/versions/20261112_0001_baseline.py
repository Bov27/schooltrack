"""Baseline: extensions, tenant-context functions and runtime-role access.

Revision ID: 0001
Revises:
Create Date: 2026-11-12

Tables arrive in later migrations, one module at a time, following
docs/database/schema.sql.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "schooltrack_app"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # Return NULL when the setting is missing, so RLS policies fail closed.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_institution_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.current_institution_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
        $$
        """
    )

    # The runtime role is created outside migrations (it holds a password).
    # Fail early, with a clear message, if it is missing or could bypass RLS.
    op.execute(
        f"""
        DO $$
        DECLARE r record;
        BEGIN
            SELECT rolsuper, rolbypassrls INTO r FROM pg_roles WHERE rolname = '{APP_ROLE}';
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Role {APP_ROLE} does not exist. See infrastructure/docker/postgres/initdb.';
            END IF;
            IF r.rolsuper OR r.rolbypassrls THEN
                RAISE EXCEPTION 'Role {APP_ROLE} must be NOSUPERUSER NOBYPASSRLS so RLS applies to it.';
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app_current_institution_id()")
    # Extensions are left in place: other objects may depend on them.
