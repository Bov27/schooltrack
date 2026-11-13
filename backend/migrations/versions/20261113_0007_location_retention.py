"""Location retention: precise coordinates can be purged after a retention period,
keeping the validation result. Only the worker role may do it, and only that.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "schooltrack_worker"
LOCATION_FIELDS = "'location', 'gps_accuracy_m', 'location_captured_at', 'location_purged_at'"


def upgrade() -> None:
    op.execute("ALTER TABLE attendance_events ADD COLUMN location_purged_at timestamptz")
    # A purged GPS event has no location any more; it must still satisfy the constraint.
    op.execute("ALTER TABLE attendance_events DROP CONSTRAINT attendance_events_check1")
    op.execute(
        "ALTER TABLE attendance_events ADD CONSTRAINT attendance_events_location_required "
        "CHECK (source = 'MANUAL' OR location IS NOT NULL OR location_purged_at IS NOT NULL)"
    )

    # Events stay immutable. The only new exception: the worker role may clear the
    # location fields (all at once, never set them) and stamp location_purged_at.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION attendance_events_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            other_new jsonb;
            other_old jsonb;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'attendance_events is append-only'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            other_new := to_jsonb(NEW) - 'validation_status' - 'validation_reasons'
                         - ARRAY[{LOCATION_FIELDS}];
            other_old := to_jsonb(OLD) - 'validation_status' - 'validation_reasons'
                         - ARRAY[{LOCATION_FIELDS}];
            IF other_new IS DISTINCT FROM other_old THEN
                RAISE EXCEPTION 'attendance_events rows are immutable except for validation fields'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF (NEW.location, NEW.gps_accuracy_m, NEW.location_captured_at, NEW.location_purged_at)
               IS DISTINCT FROM
               (OLD.location, OLD.gps_accuracy_m, OLD.location_captured_at, OLD.location_purged_at)
            THEN
                IF current_user <> '{WORKER_ROLE}' THEN
                    RAISE EXCEPTION 'only the retention job may purge event locations'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;
                IF NEW.location IS NOT NULL OR NEW.gps_accuracy_m IS NOT NULL
                   OR NEW.location_captured_at IS NOT NULL OR NEW.location_purged_at IS NULL
                   OR OLD.location_purged_at IS NOT NULL THEN
                    RAISE EXCEPTION 'a location purge must clear every location field once'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        "CREATE INDEX attendance_events_purge_idx ON attendance_events (occurred_at) "
        "WHERE location IS NOT NULL"
    )
    # Column-level grants: the worker can touch nothing else on events.
    op.execute(f"GRANT SELECT ON attendance_events TO {WORKER_ROLE}")
    op.execute(
        "GRANT UPDATE (location, gps_accuracy_m, location_captured_at, location_purged_at) "
        f"ON attendance_events TO {WORKER_ROLE}"
    )
    op.execute(f"GRANT DELETE ON outbox_events TO {WORKER_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE DELETE ON outbox_events FROM {WORKER_ROLE}")
    op.execute(
        "REVOKE UPDATE (location, gps_accuracy_m, location_captured_at, location_purged_at) "
        f"ON attendance_events FROM {WORKER_ROLE}"
    )
    op.execute(f"REVOKE SELECT ON attendance_events FROM {WORKER_ROLE}")
    op.execute("DROP INDEX IF EXISTS attendance_events_purge_idx")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION attendance_events_guard() RETURNS trigger
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
    op.execute("ALTER TABLE attendance_events DROP CONSTRAINT attendance_events_location_required")
    op.execute(
        "ALTER TABLE attendance_events ADD CONSTRAINT attendance_events_check1 "
        "CHECK (source = 'MANUAL' OR location IS NOT NULL)"
    )
    op.execute("ALTER TABLE attendance_events DROP COLUMN location_purged_at")
