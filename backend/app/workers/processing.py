"""Background processing (ADR-005), on a synchronous psycopg connection with the worker
role. Each function processes one batch and is safe to run concurrently on several
workers: rows are claimed with FOR UPDATE SKIP LOCKED.

    outbox_events --dispatch--> notifications --deliver--> push provider
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.workers.push import PushMessage, PushSender

logger = logging.getLogger("schooltrack.worker")

OUTBOX_MAX_ATTEMPTS = 10
Handler = Callable[[psycopg.Connection[Any], dict[str, Any]], int]

_EVENT_TEXT = {
    "CHECK_IN": ("llegó a", "Llegada"),
    "CHECK_OUT": ("salió de", "Salida"),
    "TEMPORARY_CHECK_OUT": ("salió temporalmente de", "Salida temporal"),
    "RETURN": ("regresó a", "Regreso"),
}


def backoff_seconds(attempts: int) -> int:
    """30 s, 1 min, 2 min, 4 min, ... capped at 1 h."""
    return int(min(30 * 2 ** max(attempts - 1, 0), 3600))


def notify_guardians(conn: psycopg.Connection[Any], row: dict[str, Any]) -> int:
    """attendance.event_recorded -> one notification per guardian who receives alerts."""
    payload = row["payload"]
    with conn.cursor(row_factory=dict_row) as cur:
        recipients = cur.execute(
            """
            SELECT g.user_id, s.full_name AS student, c.name AS campus, i.timezone
            FROM student_guardians sg
            JOIN guardians g ON g.institution_id = sg.institution_id AND g.id = sg.guardian_id
            JOIN students s ON s.institution_id = sg.institution_id AND s.id = sg.student_id
            JOIN campuses c ON c.institution_id = sg.institution_id AND c.id = %(campus)s::uuid
            JOIN institutions i ON i.id = sg.institution_id
            WHERE sg.institution_id = %(inst)s AND sg.student_id = %(student)s::uuid
              AND sg.receives_alerts
            """,
            {
                "inst": row["institution_id"],
                "student": payload["student_id"],
                "campus": payload["campus_id"],
            },
        ).fetchall()
        created = 0
        verb, kind_label = _EVENT_TEXT.get(payload["event_type"], ("registró en", "Asistencia"))
        for r in recipients:
            occurred = datetime.fromisoformat(payload["occurred_at"])
            when = occurred.astimezone(ZoneInfo(r["timezone"]))
            first_name = r["student"].split(" ")[0]
            title = f"{kind_label}: {first_name}"
            body = f"{r['student']} {verb} {r['campus']} a las {when:%H:%M}."
            if payload.get("validation_status") == "FLAGGED_FOR_REVIEW":
                body += " El registro está en revisión."
            cur.execute(
                """
                INSERT INTO notifications (institution_id, recipient_user_id, kind, title, body,
                                           payload, source_outbox_id)
                VALUES (%s, %s, 'ATTENDANCE_EVENT', %s, %s, %s, %s)
                ON CONFLICT (source_outbox_id, recipient_user_id) DO NOTHING
                """,
                (
                    row["institution_id"],
                    r["user_id"],
                    title,
                    body,
                    Jsonb({"event_id": payload["event_id"], "student_id": payload["student_id"]}),
                    row["id"],
                ),
            )
            created += cur.rowcount
    return created


HANDLERS: dict[str, Handler] = {"attendance.event_recorded": notify_guardians}


def dispatch_outbox(
    conn: psycopg.Connection[Any],
    batch_size: int = 100,
    handlers: dict[str, Handler] | None = None,
) -> int:
    """Process due outbox rows. A failing row is retried later with backoff and does not
    block the rest of the batch. Returns the number of rows processed successfully."""
    handlers = handlers or HANDLERS
    processed = 0
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT id, institution_id, topic, payload, attempts FROM outbox_events
            WHERE processed_at IS NULL AND available_at <= now() AND attempts < %s
            ORDER BY id LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (OUTBOX_MAX_ATTEMPTS, batch_size),
        ).fetchall()
        for row in rows:
            handler = handlers.get(row["topic"])
            try:
                with conn.transaction():  # savepoint: a failure undoes only this row
                    if handler is None:
                        raise LookupError(f"no handler for topic {row['topic']!r}")
                    handler(conn, row)
                    cur.execute(
                        "UPDATE outbox_events SET processed_at = now() WHERE id = %s",
                        (row["id"],),
                    )
                processed += 1
            except Exception as exc:  # one bad message must not stop the others
                attempts = row["attempts"] + 1
                logger.warning("outbox %s failed (attempt %s): %s", row["id"], attempts, exc)
                cur.execute(
                    """
                    UPDATE outbox_events
                    SET attempts = %s, last_error = %s,
                        available_at = now() + make_interval(secs => %s)
                    WHERE id = %s
                    """,
                    (
                        attempts,
                        f"{type(exc).__name__}: {exc}"[:500],
                        backoff_seconds(attempts),
                        row["id"],
                    ),
                )
    return processed


def deliver_notifications(
    conn: psycopg.Connection[Any],
    sender: PushSender,
    *,
    max_attempts: int,
    batch_size: int = 100,
) -> int:
    """Send due notifications to the recipients' active devices. Notifications for users
    without a push-enabled device are kept in-app only (marked SENT). Returns the number
    of notifications marked SENT."""
    sent = 0
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT id, recipient_user_id, title, body, payload, attempts FROM notifications
            WHERE status = 'PENDING' AND next_attempt_at <= now()
            ORDER BY next_attempt_at LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (batch_size,),
        ).fetchall()
        for row in rows:
            tokens = [
                t["push_token"]
                for t in cur.execute(
                    "SELECT push_token FROM devices WHERE user_id = %s AND status = 'ACTIVE' "
                    "AND push_token IS NOT NULL",
                    (row["recipient_user_id"],),
                ).fetchall()
            ]
            results = sender.send(
                [
                    PushMessage(
                        token,
                        row["title"],
                        row["body"],
                        {**row["payload"], "notification_id": str(row["id"])},
                    )
                    for token in tokens
                ]
            )
            errors = [r.error for r in results if not r.ok]
            if not tokens or len(errors) < len(results):
                # Delivered to at least one device, or in-app only.
                cur.execute(
                    "UPDATE notifications SET status = 'SENT', sent_at = now(), attempts = %s, "
                    "last_error = %s WHERE id = %s",
                    (row["attempts"] + 1, "; ".join(e or "" for e in errors) or None, row["id"]),
                )
                sent += 1
                continue
            attempts = row["attempts"] + 1
            final = attempts >= max_attempts
            cur.execute(
                """
                UPDATE notifications
                SET attempts = %s, last_error = %s,
                    status = CASE WHEN %s THEN 'FAILED'::notification_status ELSE status END,
                    next_attempt_at = now() + make_interval(secs => %s)
                WHERE id = %s
                """,
                (
                    attempts,
                    "; ".join(e or "" for e in errors)[:500],
                    final,
                    backoff_seconds(attempts),
                    row["id"],
                ),
            )
    return sent
