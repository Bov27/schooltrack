"""Fictional demo data: one institution with people, a geofence and two weeks of attendance.

Everything here is invented (names, codes, e-mails under the reserved ``.test`` domain).
It runs with the owner connection, like the other operational commands, and refuses to
run twice so it can never overwrite real data.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from app.core.security import hash_password

DEMO_SLUG = "colegio-demo"
DEMO_DOMAIN = "demo.schooltrack.test"
TIMEZONE = ZoneInfo("America/Bogota")
# Half the side of the square geofence, in degrees (about 130 m at Popayán's latitude).
HALF_SIDE_DEG = 0.0012

STUDENT_NAMES = (
    "Valentina Muñoz",
    "Santiago Rivera",
    "Isabella Paz",
    "Mateo Ordóñez",
    "Mariana Velasco",
    "Samuel Chicangana",
    "Sofía Burbano",
    "Emiliano Caicedo",
)


@dataclass(frozen=True)
class DemoAccount:
    email: str
    role: str
    description: str


ACCOUNTS = (
    DemoAccount(f"rectoria@{DEMO_DOMAIN}", "SCHOOL_ADMIN", "School administrator (dashboard)"),
    DemoAccount(f"docente@{DEMO_DOMAIN}", "TEACHER", "Teacher with staff attendance (app)"),
    DemoAccount(f"estudiante@{DEMO_DOMAIN}", "STUDENT", "Student: Valentina Muñoz (app)"),
    DemoAccount(f"acudiente@{DEMO_DOMAIN}", "GUARDIAN", "Guardian of Valentina and Santiago (app)"),
)


@dataclass(frozen=True)
class _Campus:
    institution_id: uuid.UUID
    campus_id: uuid.UUID
    geofence_id: uuid.UUID
    center: tuple[float, float]


class DemoAlreadyExistsError(Exception):
    pass


def _school_days(today: date, count: int) -> list[date]:
    days: list[date] = []
    day = today - timedelta(days=1)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def _at(day: date, start: time, spread_min: int, rng: random.Random) -> datetime:
    local = datetime.combine(day, start, TIMEZONE) + timedelta(minutes=rng.randint(0, spread_min))
    return local.astimezone(UTC)


class _Seeder:
    def __init__(self, conn: psycopg.Connection[Any], rng: random.Random) -> None:
        self.conn = conn
        self.rng = rng

    def one(self, sql: str, params: tuple[Any, ...]) -> uuid.UUID:
        row = self.conn.execute(sql, params).fetchone()
        if row is None:  # pragma: no cover - every statement here uses RETURNING
            raise RuntimeError("expected a row")
        value: uuid.UUID = row[0]
        return value

    def user(self, email: str, name: str, password_hash: str) -> uuid.UUID:
        return self.one(
            "INSERT INTO users (email, full_name, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (email, name, password_hash),
        )

    def member(self, inst: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
        self.conn.execute(
            "INSERT INTO institution_memberships (institution_id, user_id, status) "
            "VALUES (%s, %s, 'ACTIVE')",
            (inst, user_id),
        )
        self.conn.execute(
            "INSERT INTO user_roles (institution_id, user_id, role) VALUES (%s, %s, %s)",
            (inst, user_id, role),
        )

    def point(self, lat: float, lng: float) -> str:
        inner = HALF_SIDE_DEG * 0.6
        return (
            f"SRID=4326;POINT({lng + self.rng.uniform(-inner, inner):.6f} "
            f"{lat + self.rng.uniform(-inner, inner):.6f})"
        )

    def event(
        self,
        where: _Campus,
        subject: tuple[str, uuid.UUID],
        *,
        actor: uuid.UUID,
        event_type: str,
        before: str,
        after: str,
        at: datetime,
        flagged: bool = False,
    ) -> uuid.UUID:
        column, subject_id = subject
        return self.one(
            f"""
            INSERT INTO attendance_events (institution_id, campus_id, {column}, actor_user_id,
                event_type, source, state_before, state_after, occurred_at, received_at,
                location, gps_accuracy_m, location_captured_at, is_mock_location,
                geofence_id, geofence_result, distance_to_geofence_m,
                idempotency_key, validation_status, validation_reasons)
            VALUES (%s, %s, %s, %s, %s, 'MOBILE_GPS', %s, %s, %s, %s,
                ST_GeogFromText(%s), %s, %s, false,
                %s, 'INSIDE', 0, gen_random_uuid(), %s, %s::jsonb)
            RETURNING id
            """,  # noqa: S608 - column is one of two fixed names
            (
                where.institution_id,
                where.campus_id,
                subject_id,
                actor,
                event_type,
                before,
                after,
                at,
                at + timedelta(seconds=self.rng.randint(1, 4)),
                self.point(*where.center),
                round(self.rng.uniform(6, 22), 1),
                at,
                where.geofence_id,
                "FLAGGED_FOR_REVIEW" if flagged else "VALIDATED",
                '["BOUNDARY_UNCERTAIN"]' if flagged else "[]",
            ),
        )


def seed_demo(
    conn: psycopg.Connection[Any],
    password: str,
    *,
    center: tuple[float, float] = (2.4419, -76.6063),
    days: int = 10,
    today: date | None = None,
    rng_seed: int = 7,
) -> uuid.UUID:
    """Create the demo institution inside the caller's transaction and return its id."""
    if conn.execute("SELECT 1 FROM institutions WHERE slug = %s", (DEMO_SLUG,)).fetchone():
        raise DemoAlreadyExistsError(f"The demo institution '{DEMO_SLUG}' already exists")

    rng = random.Random(rng_seed)  # noqa: S311 - demo data, not security
    seeder = _Seeder(conn, rng)
    password_hash = hash_password(password)
    lat, lng = center

    inst = seeder.one(
        "INSERT INTO institutions (name, slug) VALUES (%s, %s) RETURNING id",
        ("Colegio Demo Los Andes", DEMO_SLUG),
    )
    campus = seeder.one(
        "INSERT INTO campuses (institution_id, name) VALUES (%s, 'Sede Principal') RETURNING id",
        (inst,),
    )
    d = HALF_SIDE_DEG
    ring = [(lng - d, lat - d), (lng + d, lat - d), (lng + d, lat + d), (lng - d, lat + d)]
    ring.append(ring[0])
    wkt = "SRID=4326;POLYGON((" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in ring) + "))"
    geofence = seeder.one(
        "INSERT INTO geofences (institution_id, campus_id, name, area) "
        "VALUES (%s, %s, 'Perímetro del colegio', ST_GeogFromText(%s)) RETURNING id",
        (inst, campus, wkt),
    )

    admin = seeder.user(ACCOUNTS[0].email, "Rectoría Demo", password_hash)
    seeder.member(inst, admin, "SCHOOL_ADMIN")
    teacher_user = seeder.user(ACCOUNTS[1].email, "Laura Docente Demo", password_hash)
    seeder.member(inst, teacher_user, "TEACHER")
    teacher = seeder.one(
        "INSERT INTO staff (institution_id, employee_code, staff_type, user_id) "
        "VALUES (%s, 'DOC-001', 'TEACHER', %s) RETURNING id",
        (inst, teacher_user),
    )
    student_user = seeder.user(ACCOUNTS[2].email, STUDENT_NAMES[0], password_hash)
    seeder.member(inst, student_user, "STUDENT")

    students: list[tuple[uuid.UUID, uuid.UUID]] = []  # (student id, actor user id)
    for index, name in enumerate(STUDENT_NAMES):
        linked = student_user if index == 0 else None
        student_id = seeder.one(
            "INSERT INTO students (institution_id, student_code, full_name, user_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (inst, f"EST-{index + 1:03d}", name, linked),
        )
        # Students without their own account were recorded by the teacher in this demo.
        students.append((student_id, linked or teacher_user))

    guardian_user = seeder.user(ACCOUNTS[3].email, "Carmen Acudiente Demo", password_hash)
    seeder.member(inst, guardian_user, "GUARDIAN")
    guardian = seeder.one(
        "INSERT INTO guardians (institution_id, user_id) VALUES (%s, %s) RETURNING id",
        (inst, guardian_user),
    )
    for student_id, _ in students[:2]:
        conn.execute(
            "INSERT INTO student_guardians (institution_id, student_id, guardian_id, "
            "relationship, authorized_by) VALUES (%s, %s, %s, 'MOTHER', %s)",
            (inst, student_id, guardian, admin),
        )

    # History: every subject ends each day OUTSIDE, so today starts clean.
    subjects: list[tuple[tuple[str, uuid.UUID], uuid.UUID, float]] = [
        (("student_id", sid), actor, 0.88) for sid, actor in students
    ]
    subjects.append((("staff_id", teacher), teacher_user, 0.97))
    where = _Campus(inst, campus, geofence, center)
    last_event: dict[uuid.UUID, uuid.UUID] = {}
    for day in _school_days(today or datetime.now(TIMEZONE).date(), days):
        for subject, actor, attendance_rate in subjects:
            if rng.random() > attendance_rate:
                continue  # absent that day
            seeder.event(
                where,
                subject,
                actor=actor,
                event_type="CHECK_IN",
                before="OUTSIDE",
                after="PRESENT",
                at=_at(day, time(6, 40), 40, rng),
                flagged=rng.random() < 0.08,
            )
            last_event[subject[1]] = seeder.event(
                where,
                subject,
                actor=actor,
                event_type="CHECK_OUT",
                before="PRESENT",
                after="OUTSIDE",
                at=_at(day, time(12, 30), 45, rng),
            )

    for subject, _, _ in subjects:
        column, subject_id = subject
        conn.execute(
            f"INSERT INTO attendance_subject_states (institution_id, {column}, current_state, "  # noqa: S608
            "last_event_id) VALUES (%s, %s, 'OUTSIDE', %s)",
            (inst, subject_id, last_event.get(subject_id)),
        )
    return inst
