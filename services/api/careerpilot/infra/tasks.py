"""Background task dispatch.

Tasks are plain functions registered by name. In `inline` mode they run synchronously in the calling
process (development/tests). In `celery` mode they are sent to the Celery worker (see careerpilot.worker).
Each run is tracked in `background_tasks` so failures can be inspected and retried by admins.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from careerpilot.config import get_settings
from careerpilot.db import session_factory, utcnow
from careerpilot.models import BackgroundTask

logger = logging.getLogger(__name__)

TaskFn = Callable[..., None]
REGISTRY: dict[str, TaskFn] = {}
MAX_ATTEMPTS = 3


def task(name: str) -> Callable[[TaskFn], TaskFn]:
    def decorator(fn: TaskFn) -> TaskFn:
        REGISTRY[name] = fn
        return fn

    return decorator


def run_tracked(name: str, task_id: str, kwargs: dict[str, Any]) -> None:
    """Execute a registered task, recording status. Exceptions are recorded, never propagated raw."""
    db = session_factory()()
    try:
        record = db.get(BackgroundTask, uuid.UUID(task_id))
        if record is None:
            return
        record.status = "running"
        record.attempts += 1
        db.commit()
        try:
            REGISTRY[name](**kwargs)
            record.status = "succeeded"
            record.last_error = None
        except Exception as exc:
            logger.exception("background_task_failed", extra={"task": name, "task_id": task_id})
            record.status = "failed"
            record.last_error = type(exc).__name__[:500]
        record.finished_at = utcnow()
        db.commit()
    finally:
        db.close()


def enqueue(name: str, *, entity_type: str | None = None, entity_id: str | None = None, **kwargs: Any) -> str:
    if name not in REGISTRY:
        raise KeyError(f"unknown task {name}")
    db = session_factory()()
    try:
        record = BackgroundTask(name=name, entity_type=entity_type, entity_id=entity_id, status="queued")
        db.add(record)
        db.commit()
        task_id = str(record.id)
    finally:
        db.close()

    if get_settings().task_mode == "celery":
        from careerpilot.worker import celery_app

        celery_app.send_task("careerpilot.run", args=[name, task_id, kwargs])
    else:
        run_tracked(name, task_id, kwargs)
    return task_id
