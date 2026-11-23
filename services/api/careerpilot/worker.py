"""Celery worker entry point. Run: celery -A careerpilot.worker worker --loglevel=INFO

Tasks are registered by name in careerpilot.infra.tasks.REGISTRY and executed through run_tracked so
that status, attempts and safe error summaries are persisted in `background_tasks`.
"""

from __future__ import annotations

from typing import Any

from celery import Celery

from careerpilot.config import get_settings
from careerpilot.logging_config import configure_logging

_settings = get_settings()
celery_app = Celery("careerpilot", broker=_settings.redis_url or "redis://localhost:6379/0")
celery_app.conf.update(
    task_acks_late=True,  # re-deliver if the worker dies mid-task
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)


@celery_app.task(name="careerpilot.run", bind=True, max_retries=2, default_retry_delay=30)
def run(self: Any, name: str, task_id: str, kwargs: dict[str, Any]) -> None:
    from careerpilot.infra.tasks import run_tracked

    run_tracked(name, task_id, kwargs)


def _init() -> None:
    configure_logging(_settings.log_level)
    import careerpilot.services.resumes  # noqa: F401  (registers tasks)


_init()
