"""Privacy retention: precise coordinates are purged after the retention period by the
worker role only; the validation result and the rest of the event stay intact."""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from app.workers.processing import delete_processed_outbox, purge_expired_locations
from tests.db_support import Factory, requires_database

pytestmark = [
    requires_database,
    pytest.mark.skipif(
        not os.environ.get("WORKER_DATABASE_URL"), reason="needs WORKER_DATABASE_URL"
    ),
]


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def worker_conn(owner_conn: Any) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(_dsn("WORKER_DATABASE_URL")) as conn:
        yield conn


def add_event(owner_conn: Any, factory: Factory, days_ago: int) -> uuid.UUID:
    inst = owner_conn.execute("SELECT id FROM institutions LIMIT 1").fetchone()
    if inst is None:
        inst_id = factory.institution("colegio-a")
        user = factory.user("ana@colegio-a.test")
        factory.member(inst_id, user, "STUDENT")
        factory.student(inst_id, "A-001", user)
        factory.campus(inst_id, "Sede Centro")
    row = owner_conn.execute(
        """
        INSERT INTO attendance_events (institution_id, campus_id, student_id, actor_user_id,
            event_type, source, state_before, state_after, occurred_at, location,
            gps_accuracy_m, location_captured_at, idempotency_key, validation_status,
            geofence_result, distance_to_geofence_m)
        SELECT s.institution_id, c.id, s.id, s.user_id, 'CHECK_IN', 'MOBILE_GPS', 'OUTSIDE',
               'PRESENT', now() - make_interval(days => %s),
               ST_GeogFromText('SRID=4326;POINT(-76.6063 2.4419)'), 7,
               now() - make_interval(days => %s), gen_random_uuid(), 'VALIDATED', 'INSIDE', 0
        FROM students s JOIN campuses c ON c.institution_id = s.institution_id
        LIMIT 1
        RETURNING id
        """,
        (days_ago, days_ago),
    ).fetchone()
    assert row is not None
    event_id: uuid.UUID = row[0]
    return event_id


def location_of(owner_conn: Any, event_id: uuid.UUID) -> tuple[Any, ...]:
    row = owner_conn.execute(
        "SELECT location IS NULL, gps_accuracy_m, location_purged_at IS NOT NULL, "
        "geofence_result::text, validation_status::text, event_type::text "
        "FROM attendance_events WHERE id = %s",
        (event_id,),
    ).fetchone()
    assert row is not None
    return tuple(row)


def test_old_locations_are_purged_and_recent_ones_kept(
    owner_conn: Any, worker_conn: Any, factory: Factory
) -> None:
    old = add_event(owner_conn, factory, days_ago=120)
    recent = add_event(owner_conn, factory, days_ago=10)
    assert purge_expired_locations(worker_conn, retention_days=90) == 1
    assert location_of(owner_conn, old) == (True, None, True, "INSIDE", "VALIDATED", "CHECK_IN")
    assert location_of(owner_conn, recent)[:3] == (False, 7.0, False)
    assert purge_expired_locations(worker_conn, retention_days=90) == 0  # idempotent


def test_only_the_worker_may_purge(owner_conn: Any, factory: Factory) -> None:
    event_id = add_event(owner_conn, factory, days_ago=120)
    purge = (
        "UPDATE attendance_events SET location = NULL, gps_accuracy_m = NULL, "
        "location_captured_at = NULL, location_purged_at = now() WHERE id = %s"
    )
    # Not even the owner/superuser connection.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute(purge, (event_id,))
    # The API role, with the tenant context set so that RLS lets it see the row.
    institution = owner_conn.execute(
        "SELECT institution_id::text FROM attendance_events WHERE id = %s", (event_id,)
    ).fetchone()[0]
    with psycopg.connect(_dsn("DATABASE_URL")) as app_conn:
        app_conn.execute(
            "SELECT set_config('app.current_institution_id', %s, true)", (institution,)
        )
        visible = app_conn.execute(
            "SELECT count(*) FROM attendance_events WHERE id = %s", (event_id,)
        ).fetchone()
        assert visible == (1,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app_conn.execute(purge, (event_id,))


def test_worker_cannot_alter_anything_else(
    owner_conn: Any, worker_conn: Any, factory: Factory
) -> None:
    event_id = add_event(owner_conn, factory, days_ago=120)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker_conn.execute(
            "UPDATE attendance_events SET event_type = 'CHECK_OUT' WHERE id = %s", (event_id,)
        )
    worker_conn.rollback()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker_conn.execute(
            "UPDATE attendance_events SET location = NULL, location_purged_at = now() "
            "WHERE id = %s",
            (event_id,),
        )


def test_processed_outbox_rows_are_deleted_after_retention(
    owner_conn: Any, worker_conn: Any, factory: Factory
) -> None:
    inst = factory.institution("colegio-a")
    owner_conn.execute(
        """
        INSERT INTO outbox_events (institution_id, topic, payload, processed_at)
        VALUES (%s, 't', '{}', now() - interval '40 days'),
               (%s, 't', '{}', now() - interval '1 day'),
               (%s, 't', '{}', NULL)
        """,
        (inst, inst, inst),
    )
    assert delete_processed_outbox(worker_conn, retention_days=30) == 1
    remaining = owner_conn.execute("SELECT count(*) FROM outbox_events").fetchone()
    assert remaining == (2,)
