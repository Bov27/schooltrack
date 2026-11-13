"""Celery application: periodic outbox dispatch and notification delivery.

    celery -A app.workers.celery_app worker --loglevel=INFO
    celery -A app.workers.celery_app beat --loglevel=INFO
"""

from typing import Any

import psycopg
from celery import Celery

from app.core.config import get_settings
from app.workers.processing import deliver_notifications, dispatch_outbox
from app.workers.push import sender_for

settings = get_settings()

app = Celery("schooltrack", broker=settings.redis_url or "memory://")
app.conf.update(
    task_acks_late=True,  # a task that dies mid-way is redelivered; processing is idempotent
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    timezone="UTC",
    beat_schedule={
        "dispatch-outbox": {"task": "schooltrack.dispatch_outbox", "schedule": 5.0},
        "deliver-notifications": {"task": "schooltrack.deliver_notifications", "schedule": 10.0},
    },
)


def _connect() -> psycopg.Connection[Any]:
    if settings.worker_database_url is None:
        raise RuntimeError("WORKER_DATABASE_URL is not configured")
    dsn = str(settings.worker_database_url).replace("postgresql+psycopg://", "postgresql://", 1)
    return psycopg.connect(dsn)


@app.task(name="schooltrack.dispatch_outbox")
def dispatch_outbox_task() -> int:
    with _connect() as conn:
        return dispatch_outbox(conn)


@app.task(name="schooltrack.deliver_notifications")
def deliver_notifications_task() -> int:
    with _connect() as conn:
        return deliver_notifications(
            conn,
            sender_for(settings.push_provider),
            max_attempts=settings.notification_max_attempts,
        )
