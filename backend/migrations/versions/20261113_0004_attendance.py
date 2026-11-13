"""Attendance engine: devices, students, staff, attendance events and states, audit log.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "schooltrack_app"
PLATFORM_ROLE = "schooltrack_platform"
TENANT_TABLES = ("students", "staff", "attendance_events", "attendance_subject_states", "audit_logs")


def upgrade() -> None:
    op.execute("CREATE TYPE staff_type AS ENUM ('TEACHER', 'ADMINISTRATIVE', 'SUPPORT')")
    op.execute(
        "CREATE TYPE attendance_event_type AS ENUM "
        "('CHECK_IN', 'TEMPORARY_CHECK_OUT', 'RETURN', 'CHECK_OUT')"
    )
    op.execute("CREATE TYPE attendance_state AS ENUM ('OUTSIDE', 'PRESENT', 'TEMPORARY_EXIT')")
    op.execute("CREATE TYPE attendance_source AS ENUM ('MOBILE_GPS', 'MANUAL', 'OFFLINE_SYNC')")
    op.execute("CREATE TYPE geofence_result AS ENUM ('INSIDE', 'OUTSIDE', 'NOT_EVALUATED')")
    op.execute(
        "CREATE TYPE validation_status AS ENUM "
        "('PENDING', 'VALIDATED', 'REJECTED', 'FLAGGED_FOR_REVIEW')"
    )
    op.execute("CREATE TYPE device_platform AS ENUM ('ANDROID', 'IOS', 'WEB')")
    op.execute("CREATE TYPE device_status AS ENUM ('ACTIVE', 'REVOKED')")

    # ---- devices (global, owned by a user) ----------------------------------------
    op.execute(
        """
        CREATE TABLE devices (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            installation_id  text NOT NULL CHECK (length(installation_id) BETWEEN 8 AND 200),
            platform         device_platform NOT NULL,
            model            text,
            app_version      text,
            status           device_status NOT NULL DEFAULT 'ACTIVE',
            registered_at    timestamptz NOT NULL DEFAULT now(),
            last_seen_at     timestamptz,
            UNIQUE (user_id, installation_id)
        )
        """
    )

    # ---- people ------------------------------------------------------------------
    # A student's account is optional (young children); when present it must be a
    # member of the same institution (composite FK, not checked while user_id is NULL).
    op.execute(
        """
        CREATE TABLE students (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id  uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            user_id         uuid,
            student_code    text NOT NULL CHECK (length(btrim(student_code)) > 0),
            full_name       text NOT NULL CHECK (length(btrim(full_name)) > 0),
            date_of_birth   date,
            is_active       boolean NOT NULL DEFAULT true,
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (institution_id, student_code),
            UNIQUE (institution_id, user_id),
            UNIQUE (institution_id, id),
            FOREIGN KEY (institution_id, user_id)
                REFERENCES institution_memberships (institution_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE staff (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id  uuid NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
            user_id         uuid NOT NULL,
            employee_code   text NOT NULL CHECK (length(btrim(employee_code)) > 0),
            staff_type      staff_type NOT NULL,
            is_active       boolean NOT NULL DEFAULT true,
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (institution_id, employee_code),
            UNIQUE (institution_id, user_id),
            UNIQUE (institution_id, id),
            FOREIGN KEY (institution_id, user_id)
                REFERENCES institution_memberships (institution_id, user_id)
        )
        """
    )

    # ---- attendance --------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE attendance_events (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id        uuid NOT NULL,
            campus_id             uuid NOT NULL,
            student_id            uuid,
            staff_id              uuid,
            actor_user_id         uuid NOT NULL REFERENCES users(id),
            device_id             uuid REFERENCES devices(id),
            event_type            attendance_event_type NOT NULL,
            source                attendance_source NOT NULL,
            state_before          attendance_state NOT NULL,
            state_after           attendance_state NOT NULL,
            occurred_at           timestamptz NOT NULL,
            received_at           timestamptz NOT NULL DEFAULT now(),
            location              geography(POINT, 4326),
            gps_accuracy_m        real CHECK (gps_accuracy_m IS NULL OR gps_accuracy_m >= 0),
            location_captured_at  timestamptz,
            is_mock_location      boolean,
            geofence_id           uuid,
            geofence_result       geofence_result NOT NULL DEFAULT 'NOT_EVALUATED',
            distance_to_geofence_m real,
            idempotency_key       uuid NOT NULL,
            validation_status     validation_status NOT NULL DEFAULT 'PENDING',
            validation_reasons    jsonb NOT NULL DEFAULT '[]'::jsonb,
            manual_reason         text,
            CHECK (num_nonnulls(student_id, staff_id) = 1),
            CHECK (source = 'MANUAL' OR location IS NOT NULL),
            CHECK (source <> 'MANUAL' OR manual_reason IS NOT NULL),
            UNIQUE (institution_id, id),
            UNIQUE (institution_id, actor_user_id, idempotency_key),
            FOREIGN KEY (institution_id, campus_id)   REFERENCES campuses  (institution_id, id),
            FOREIGN KEY (institution_id, student_id)  REFERENCES students  (institution_id, id),
            FOREIGN KEY (institution_id, staff_id)    REFERENCES staff     (institution_id, id),
            FOREIGN KEY (institution_id, geofence_id) REFERENCES geofences (institution_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX attendance_events_student_time_idx ON attendance_events "
        "(institution_id, student_id, occurred_at DESC) WHERE student_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX attendance_events_staff_time_idx ON attendance_events "
        "(institution_id, staff_id, occurred_at DESC) WHERE staff_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX attendance_events_review_idx ON attendance_events "
        "(institution_id, validation_status) "
        "WHERE validation_status IN ('PENDING', 'FLAGGED_FOR_REVIEW')"
    )
    # Only the review fields may change after insert; deletes are never allowed.
    op.execute(
        """
        CREATE FUNCTION attendance_events_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'attendance_events is append-only'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF (to_jsonb(NEW) - 'validation_status' - 'validation_reasons')
               IS DISTINCT FROM (to_jsonb(OLD) - 'validation_status' - 'validation_reasons') THEN
                RAISE EXCEPTION 'attendance_events rows are immutable except for validation fields'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER attendance_events_guard BEFORE UPDATE OR DELETE ON attendance_events "
        "FOR EACH ROW EXECUTE FUNCTION attendance_events_guard()"
    )

    # One row per person; locked with SELECT ... FOR UPDATE to serialize their events.
    op.execute(
        """
        CREATE TABLE attendance_subject_states (
            institution_id  uuid NOT NULL,
            student_id      uuid,
            staff_id        uuid,
            current_state   attendance_state NOT NULL DEFAULT 'OUTSIDE',
            last_event_id   uuid,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            CHECK (num_nonnulls(student_id, staff_id) = 1),
            FOREIGN KEY (institution_id, student_id)
                REFERENCES students (institution_id, id) ON DELETE CASCADE,
            FOREIGN KEY (institution_id, staff_id)
                REFERENCES staff (institution_id, id) ON DELETE CASCADE,
            FOREIGN KEY (institution_id, last_event_id)
                REFERENCES attendance_events (institution_id, id)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX attendance_subject_states_student_uq "
        "ON attendance_subject_states (institution_id, student_id) WHERE student_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX attendance_subject_states_staff_uq "
        "ON attendance_subject_states (institution_id, staff_id) WHERE staff_id IS NOT NULL"
    )

    # ---- audit -------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE audit_logs (
            id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            institution_id  uuid REFERENCES institutions(id),
            actor_user_id   uuid REFERENCES users(id),
            action          text NOT NULL,
            entity_type     text NOT NULL,
            entity_id       text,
            changes         jsonb,
            request_id      text,
            occurred_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX audit_logs_tenant_time_idx ON audit_logs (institution_id, occurred_at DESC)"
    )
    op.execute(
        """
        CREATE FUNCTION audit_logs_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only' USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()"
    )

    # ---- RLS and grants ----------------------------------------------------------------
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (institution_id = app_current_institution_id()) "
            "WITH CHECK (institution_id = app_current_institution_id())"
        )
    # A user can see which student/staff records are theirs before a tenant is chosen.
    op.execute(
        "CREATE POLICY own_student_read ON students FOR SELECT "
        "USING (user_id = app_current_user_id())"
    )
    op.execute(
        "CREATE POLICY own_staff_read ON staff FOR SELECT USING (user_id = app_current_user_id())"
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON devices TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON students, staff TO {APP_ROLE}")
    # UPDATE on events is limited to the review fields by the trigger above.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON attendance_events TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON attendance_subject_states TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON audit_logs TO {APP_ROLE}")
    # Platform actions (e.g. creating an institution) are audited too.
    op.execute(f"GRANT SELECT, INSERT ON audit_logs TO {PLATFORM_ROLE}")


def downgrade() -> None:
    for table in ("audit_logs", "attendance_subject_states", "attendance_events", "staff",
                  "students", "devices"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")
    op.execute("DROP FUNCTION IF EXISTS attendance_events_guard()")
    for enum in ("device_status", "device_platform", "validation_status", "geofence_result",
                 "attendance_source", "attendance_state", "attendance_event_type", "staff_type"):
        op.execute(f"DROP TYPE IF EXISTS {enum}")
