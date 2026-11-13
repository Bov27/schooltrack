"""Guardians, transactional outbox and notifications; push tokens on devices.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "schooltrack_app"
WORKER_ROLE = "schooltrack_worker"
TENANT_TABLES = ("guardians", "student_guardians", "outbox_events", "notifications")


def upgrade() -> None:
    # The worker processes outbox rows of every institution, so it bypasses RLS; its
    # grants (below) are limited to what background processing needs.
    op.execute(
        f"""
        DO $$
        DECLARE r record;
        BEGIN
            SELECT rolsuper INTO r FROM pg_roles WHERE rolname = '{WORKER_ROLE}';
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Role {WORKER_ROLE} does not exist. See infrastructure/docker/postgres/initdb.';
            END IF;
            IF r.rolsuper THEN
                RAISE EXCEPTION 'Role {WORKER_ROLE} must not be a superuser.';
            END IF;
        END
        $$
        """
    )
    op.execute("CREATE TYPE notification_status AS ENUM ('PENDING', 'SENT', 'FAILED', 'CANCELLED')")

    op.execute("ALTER TABLE devices ADD COLUMN push_token text CHECK (length(push_token) <= 300)")

    op.execute(
        """
        CREATE TABLE guardians (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id  uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            user_id         uuid NOT NULL,
            phone           text,
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (institution_id, user_id),
            UNIQUE (institution_id, id),
            FOREIGN KEY (institution_id, user_id)
                REFERENCES institution_memberships (institution_id, user_id)
        )
        """
    )
    # Explicit, auditable authorization of who may follow a minor (Law 1581).
    op.execute(
        """
        CREATE TABLE student_guardians (
            institution_id   uuid NOT NULL,
            student_id       uuid NOT NULL,
            guardian_id      uuid NOT NULL,
            relationship     text NOT NULL CHECK (length(btrim(relationship)) > 0),
            receives_alerts  boolean NOT NULL DEFAULT true,
            authorized_at    timestamptz NOT NULL DEFAULT now(),
            authorized_by    uuid REFERENCES users(id),
            PRIMARY KEY (institution_id, student_id, guardian_id),
            FOREIGN KEY (institution_id, student_id)
                REFERENCES students (institution_id, id) ON DELETE CASCADE,
            FOREIGN KEY (institution_id, guardian_id)
                REFERENCES guardians (institution_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX student_guardians_guardian_idx ON student_guardians (guardian_id)")

    # Transactional outbox: written in the same transaction as the business change and
    # processed asynchronously by the worker (ADR-005).
    op.execute(
        """
        CREATE TABLE outbox_events (
            id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            institution_id  uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            topic           text NOT NULL,
            payload         jsonb NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            available_at    timestamptz NOT NULL DEFAULT now(),
            attempts        integer NOT NULL DEFAULT 0,
            last_error      text,
            processed_at    timestamptz
        )
        """
    )
    op.execute(
        "CREATE INDEX outbox_events_pending_idx ON outbox_events (available_at, id) "
        "WHERE processed_at IS NULL"
    )

    op.execute(
        """
        CREATE TABLE notifications (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id     uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            recipient_user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind               text NOT NULL,
            title              text NOT NULL,
            body               text NOT NULL,
            payload            jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_outbox_id   bigint,
            status             notification_status NOT NULL DEFAULT 'PENDING',
            attempts           smallint NOT NULL DEFAULT 0,
            next_attempt_at    timestamptz NOT NULL DEFAULT now(),
            last_error         text,
            created_at         timestamptz NOT NULL DEFAULT now(),
            sent_at            timestamptz,
            read_at            timestamptz,
            -- A redelivered outbox event must not notify the same person twice.
            UNIQUE (source_outbox_id, recipient_user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX notifications_dispatch_idx ON notifications (next_attempt_at) "
        "WHERE status = 'PENDING'"
    )
    op.execute(
        "CREATE INDEX notifications_recipient_idx ON notifications (recipient_user_id, created_at DESC)"
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (institution_id = app_current_institution_id()) "
            "WITH CHECK (institution_id = app_current_institution_id())"
        )
    # Users read (and mark as read) their own notifications from any institution.
    op.execute(
        "CREATE POLICY own_notifications_read ON notifications FOR SELECT "
        "USING (recipient_user_id = app_current_user_id())"
    )
    op.execute(
        "CREATE POLICY own_notifications_update ON notifications FOR UPDATE "
        "USING (recipient_user_id = app_current_user_id()) "
        "WITH CHECK (recipient_user_id = app_current_user_id())"
    )
    op.execute(
        "CREATE POLICY own_guardian_read ON guardians FOR SELECT "
        "USING (user_id = app_current_user_id())"
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON guardians TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON student_guardians TO {APP_ROLE}")
    op.execute(f"GRANT INSERT ON outbox_events TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON outbox_events TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, UPDATE ON notifications TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    op.execute(f"GRANT USAGE ON SCHEMA public TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, UPDATE ON outbox_events TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON notifications TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON guardians, student_guardians, students, campuses TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON devices, users, institutions TO {WORKER_ROLE}")
    op.execute(f"GRANT INSERT ON audit_logs TO {WORKER_ROLE}")


def downgrade() -> None:
    for table in ("notifications", "outbox_events", "student_guardians", "guardians"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS push_token")
    op.execute("DROP TYPE IF EXISTS notification_status")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {WORKER_ROLE}")
