"""Load test for the attendance write path (NFR-PERF-1: p95 < 300 ms at >= 50 req/s).

Simulates the school-opening burst: N students check in at once (C concurrent requests),
every phone retries once (idempotent replays), then everyone checks out. Afterwards it
verifies correctness in the database: exactly one CHECK_IN and one CHECK_OUT per student,
every state back to OUTSIDE, no server errors.

Needs a running API (BASE_URL) and the owner connection to seed fictional data:

    MIGRATIONS_DATABASE_URL=... JWT_SECRET=... DATABASE_URL=... \\
        python -m loadtest.attendance_load --base-url http://localhost:8000 --students 300
"""

import argparse
import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg

from app.core.config import Settings
from app.core.security import create_token

LAT, LNG = 2.4419, -76.6063  # Parque Caldas, Popayán (fictional school)
NFR_P95_MS = 300.0
NFR_MIN_RPS = 50.0


@dataclass
class Phase:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    seconds: float = 0.0

    def record(self, status: int, ms: float) -> None:
        self.latencies_ms.append(ms)
        self.statuses[status] = self.statuses.get(status, 0) + 1

    def percentile(self, p: float) -> float:
        ordered = sorted(self.latencies_ms)
        if not ordered:
            return 0.0
        index = min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))
        return ordered[index]

    @property
    def rps(self) -> float:
        return len(self.latencies_ms) / self.seconds if self.seconds else 0.0


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def seed(owner_dsn: str, students: int) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Fictional institution with a geofence and N students with app accounts."""
    suffix = uuid.uuid4().hex[:8]
    with psycopg.connect(owner_dsn) as conn:
        inst = conn.execute(
            "INSERT INTO institutions (name, slug) VALUES (%s, %s) RETURNING id",
            (f"Load test {suffix}", f"loadtest-{suffix}"),
        ).fetchone()[0]
        campus = conn.execute(
            "INSERT INTO campuses (institution_id, name) VALUES (%s, 'Sede') RETURNING id",
            (inst,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO geofences (institution_id, campus_id, name, area) VALUES "
            "(%s, %s, 'Perímetro', "
            "ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 150))",
            (inst, campus, LNG, LAT),
        )
        user_ids: list[uuid.UUID] = []
        with conn.cursor() as cur:
            for i in range(students):
                user_id = cur.execute(
                    "INSERT INTO users (email, full_name) VALUES (%s, %s) RETURNING id",
                    (f"load-{suffix}-{i}@example.test", f"Estudiante {i}"),
                ).fetchone()[0]
                cur.execute(
                    "INSERT INTO institution_memberships (institution_id, user_id, status) "
                    "VALUES (%s, %s, 'ACTIVE')",
                    (inst, user_id),
                )
                cur.execute(
                    "INSERT INTO user_roles (institution_id, user_id, role) "
                    "VALUES (%s, %s, 'STUDENT')",
                    (inst, user_id),
                )
                cur.execute(
                    "INSERT INTO students (institution_id, student_code, full_name, user_id) "
                    "VALUES (%s, %s, %s, %s)",
                    (inst, f"L-{i:05d}", f"Estudiante {i}", user_id),
                )
                user_ids.append(user_id)
    return inst, campus, user_ids


def event_body(event_type: str, campus: uuid.UUID, key: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "idempotency_key": key,
        "event_type": event_type,
        "campus_id": str(campus),
        "occurred_at": now.isoformat(),
        "latitude": LAT,
        "longitude": LNG,
        "accuracy_m": 8,
        "location_captured_at": (now - timedelta(seconds=1)).isoformat(),
    }


async def run_phase(
    client: httpx.AsyncClient,
    name: str,
    requests: list[tuple[dict[str, str], str, uuid.UUID, str]],
    concurrency: int,
    rate: float | None = None,
) -> Phase:
    """requests: (headers, event_type, campus_id, idempotency_key). Bodies are built at send
    time so that occurred_at is fresh (the API refuses requests older than 15 s).

    rate=None: closed loop, `concurrency` requests always in flight (saturation).
    rate=R: open loop, request i starts at i/R seconds regardless of responses (the way
    real phones arrive), with `concurrency` as an upper bound on requests in flight."""
    phase = Phase(name)
    gate = asyncio.Semaphore(concurrency)

    async def one(
        index: int, headers: dict[str, str], event_type: str, campus: uuid.UUID, key: str
    ) -> None:
        if rate is not None:
            await asyncio.sleep(max(0.0, started + index / rate - time.perf_counter()))
        async with gate:
            body = event_body(event_type, campus, key)
            started = time.perf_counter()
            try:
                response = await client.post(
                    "/api/v1/attendance/events", json=body, headers=headers
                )
                status = response.status_code
            except httpx.HTTPError:
                status = 0
            phase.record(status, (time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one(i, *request) for i, request in enumerate(requests)))
    phase.seconds = time.perf_counter() - started
    return phase


def _append_job_summary(report: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings()  # reads JWT_SECRET / DATABASE_URL from the environment
    owner_dsn = _dsn(os.environ["MIGRATIONS_DATABASE_URL"])
    inst, campus, users = seed(owner_dsn, args.students)

    headers = []
    for user_id in users:
        token, _ = create_token(settings, subject=user_id, token_type="access")  # noqa: S106
        headers.append({"Authorization": f"Bearer {token}", "X-Institution-Id": str(inst)})

    keys_in = [str(uuid.uuid4()) for _ in users]
    keys_out = [str(uuid.uuid4()) for _ in users]
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30, limits=limits) as client:
        check_in = await run_phase(
            client,
            "check-in burst",
            [(h, "CHECK_IN", campus, k) for h, k in zip(headers, keys_in, strict=True)],
            args.concurrency,
            args.rate,
        )
        retries = await run_phase(
            client,
            "retries (idempotent)",
            [(h, "CHECK_IN", campus, k) for h, k in zip(headers, keys_in, strict=True)],
            args.concurrency,
            args.rate,
        )
        check_out = await run_phase(
            client,
            "check-out burst",
            [(h, "CHECK_OUT", campus, k) for h, k in zip(headers, keys_out, strict=True)],
            args.concurrency,
            args.rate,
        )

    with psycopg.connect(owner_dsn) as conn:
        counts = dict(
            conn.execute(
                "SELECT event_type::text, count(*) FROM attendance_events "
                "WHERE institution_id = %s GROUP BY 1",
                (inst,),
            ).fetchall()
        )
        not_outside = conn.execute(
            "SELECT count(*) FROM attendance_subject_states "
            "WHERE institution_id = %s AND current_state <> 'OUTSIDE'",
            (inst,),
        ).fetchone()[0]
        validated = conn.execute(
            "SELECT count(*) FROM attendance_events WHERE institution_id = %s "
            "AND validation_status = 'VALIDATED'",
            (inst,),
        ).fetchone()[0]

    n = args.students
    problems = []
    if check_in.statuses != {201: n}:
        problems.append(f"check-in statuses {check_in.statuses} (expected all 201)")
    if retries.statuses != {200: n}:
        problems.append(f"retry statuses {retries.statuses} (expected all 200 replays)")
    if check_out.statuses != {201: n}:
        problems.append(f"check-out statuses {check_out.statuses} (expected all 201)")
    if counts != {"CHECK_IN": n, "CHECK_OUT": n}:
        problems.append(f"stored events {counts} (expected {n} of each)")
    if not_outside:
        problems.append(f"{not_outside} students not back to OUTSIDE")
    if validated != 2 * n:
        problems.append(f"{validated} validated events (expected {2 * n})")

    bursts = [check_in, check_out]
    p95 = max(p.percentile(95) for p in bursts)
    rps = min(p.rps for p in bursts)
    # The NFR is defined at an arrival rate, so it is only evaluated in open-loop runs.
    nfr_ok = args.rate is not None and p95 < NFR_P95_MS and rps >= 0.9 * NFR_MIN_RPS

    lines = [
        "## Attendance load test",
        "",
        f"{n} students, "
        + (
            f"open loop at {args.rate:.0f} req/s (max {args.concurrency} in flight)"
            if args.rate
            else f"closed loop, {args.concurrency} requests in flight (saturation)"
        )
        + f", API `{args.base_url}`",
        "",
        "| Phase | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Statuses |",
        "|---|---|---|---|---|---|---|",
    ]
    for phase in (check_in, retries, check_out):
        lines.append(
            f"| {phase.name} | {len(phase.latencies_ms)} | {phase.rps:.1f} | "
            f"{phase.percentile(50):.0f} | {phase.percentile(95):.0f} | "
            f"{phase.percentile(99):.0f} | {phase.statuses} |"
        )
    lines += [
        "",
        f"**Correctness:** {'OK' if not problems else 'FAILED: ' + '; '.join(problems)}",
        "",
        (
            f"**NFR-PERF-1** (p95 < {NFR_P95_MS:.0f} ms at {NFR_MIN_RPS:.0f} req/s): "
            f"{'met' if nfr_ok else 'NOT met'} (worst burst p95 {p95:.0f} ms, "
            f"achieved {rps:.1f} req/s)"
            if args.rate
            else f"**Saturation:** worst burst p95 {p95:.0f} ms at {rps:.1f} req/s "
            "(NFR-PERF-1 is evaluated in the open-loop run)"
        ),
    ]
    report = "\n".join(lines)
    print(report)
    _append_job_summary(report)
    if problems:
        return 1
    if args.enforce_nfr and not nfr_ok:
        return 2
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--students", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument(
        "--rate", type=float, default=None, help="open-loop arrival rate in req/s"
    )
    parser.add_argument(
        "--enforce-nfr", action="store_true", help="exit 2 if NFR-PERF-1 is missed"
    )
    sys.exit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
