"""Identity and institutions: users, refresh tokens, platform admins, institutions,
memberships, roles and campuses, with Row-Level Security.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "schooltrack_app"
PLATFORM_ROLE = "schooltrack_platform"

TENANT_TABLES = ("institution_memberships", "user_roles", "campuses")


def upgrade() -> None:
    # The platform role (BYPASSRLS, Super-Admin endpoints only) is created with the
    # runtime role by infrastructure/docker/postgres/initdb. It must not be a superuser.
    op.execute(
        f"""
        DO $$
        DECLARE r record;
        BEGIN
            SELECT rolsuper INTO r FROM pg_roles WHERE rolname = '{PLATFORM_ROLE}';
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Role {PLATFORM_ROLE} does not exist. See infrastructure/docker/postgres/initdb.';
            END IF;
            IF r.rolsuper THEN
                RAISE EXCEPTION 'Role {PLATFORM_ROLE} must not be a superuser.';
            END IF;
        END
        $$
        """
    )

    op.execute(
        "CREATE TYPE institution_role AS ENUM "
        "('SCHOOL_ADMIN', 'TEACHER', 'STUDENT', 'STAFF', 'GUARDIAN')"
    )
    op.execute("CREATE TYPE membership_status AS ENUM ('INVITED', 'ACTIVE', 'SUSPENDED')")

    # ---- global tables -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE institutions (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name        text NOT NULL CHECK (length(btrim(name)) > 0),
            slug        citext NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
            country     char(2) NOT NULL DEFAULT 'CO',
            timezone    text NOT NULL DEFAULT 'America/Bogota',
            is_active   boolean NOT NULL DEFAULT true,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE users (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email           citext NOT NULL UNIQUE,
            password_hash   text,
            full_name       text NOT NULL,
            is_active       boolean NOT NULL DEFAULT true,
            last_login_at   timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE platform_admins (
            user_id     uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            granted_at  timestamptz NOT NULL DEFAULT now(),
            granted_by  uuid REFERENCES users(id)
        )
        """
    )
    # One row per issued refresh token (the JWT carries its id). Tokens of one login
    # share a family_id so that reuse of a rotated token revokes the whole family.
    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id           uuid PRIMARY KEY,
            user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            family_id    uuid NOT NULL,
            expires_at   timestamptz NOT NULL,
            revoked_at   timestamptz,
            replaced_by  uuid REFERENCES refresh_tokens(id),
            created_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id)")
    op.execute("CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id)")

    # ---- tenant tables -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE institution_memberships (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id  uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status          membership_status NOT NULL DEFAULT 'INVITED',
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (institution_id, user_id),
            UNIQUE (institution_id, id)
        )
        """
    )
    op.execute("CREATE INDEX institution_memberships_user_idx ON institution_memberships (user_id)")
    op.execute(
        """
        CREATE TABLE user_roles (
            institution_id  uuid NOT NULL,
            user_id         uuid NOT NULL,
            role            institution_role NOT NULL,
            granted_at      timestamptz NOT NULL DEFAULT now(),
            granted_by      uuid REFERENCES users(id),
            PRIMARY KEY (institution_id, user_id, role),
            FOREIGN KEY (institution_id, user_id)
                REFERENCES institution_memberships (institution_id, user_id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX user_roles_user_idx ON user_roles (user_id)")
    op.execute(
        """
        CREATE TABLE campuses (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id  uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            name            text NOT NULL CHECK (length(btrim(name)) > 0),
            address         text,
            timezone        text,
            is_active       boolean NOT NULL DEFAULT true,
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (institution_id, name),
            UNIQUE (institution_id, id)
        )
        """
    )

    # ---- Row-Level Security --------------------------------------------------------
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (institution_id = app_current_institution_id()) "
            "WITH CHECK (institution_id = app_current_institution_id())"
        )

    op.execute("ALTER TABLE institutions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE institutions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON institutions "
        "USING (id = app_current_institution_id()) "
        "WITH CHECK (id = app_current_institution_id())"
    )

    # Before a tenant is chosen only app.current_user_id is set: users may read their own
    # memberships, roles and the institutions where they are active members.
    op.execute(
        "CREATE POLICY own_memberships_read ON institution_memberships FOR SELECT "
        "USING (user_id = app_current_user_id())"
    )
    op.execute(
        "CREATE POLICY own_roles_read ON user_roles FOR SELECT "
        "USING (user_id = app_current_user_id())"
    )
    op.execute(
        """
        CREATE POLICY member_institutions_read ON institutions FOR SELECT
        USING (id IN (SELECT m.institution_id FROM institution_memberships m
                      WHERE m.user_id = app_current_user_id() AND m.status = 'ACTIVE'))
        """
    )

    # ---- privileges ----------------------------------------------------------------
    # Runtime role: no INSERT on institutions or platform_admins (platform operations).
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON users TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON platform_admins TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON refresh_tokens TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, UPDATE ON institutions TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON institution_memberships TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON user_roles TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON campuses TO {APP_ROLE}")

    # Platform role: tenant lifecycle across institutions.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {PLATFORM_ROLE}")
    op.execute(f"GRANT SELECT ON users, platform_admins TO {PLATFORM_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON institutions TO {PLATFORM_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON institution_memberships TO {PLATFORM_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON user_roles TO {PLATFORM_ROLE}")
    op.execute(f"GRANT SELECT ON campuses TO {PLATFORM_ROLE}")


def downgrade() -> None:
    for table in ("campuses", "user_roles", "institution_memberships", "refresh_tokens",
                  "platform_admins", "users", "institutions"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TYPE IF EXISTS membership_status")
    op.execute("DROP TYPE IF EXISTS institution_role")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {PLATFORM_ROLE}")
