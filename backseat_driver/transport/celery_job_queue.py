"""Celery/RabbitMQ adapter for the `JobQueue` port: the producing side.

Celery runs the workers (`backseat_driver.tasks`); the broker configuration they share is in
`celery_app.py`. Tasks are addressed by name, so the API can enqueue work without importing the
worker code (and therefore without torch or nuscenes-devkit). Celery is imported lazily, so unit
tests and the batch CLI never need it.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.celery_app import CAPTION_TASK, INGEST_TASK, make_celery_app
from backseat_driver.transport.job_queue import JobQueue

if TYPE_CHECKING:
    from celery import Celery


class CeleryJobQueue(JobQueue):
    """`JobQueue` that publishes to RabbitMQ through Celery. Constructing it never connects."""

    def __init__(self, broker_url: str, make_app: Callable[[str], Any] = make_celery_app) -> None:
        self._broker_url = broker_url
        self._make_app = make_app
        self._app: Celery | None = None

    def enqueue_ingest(self, task: IngestTask) -> None:
        self._get_app().send_task(INGEST_TASK, args=[task.model_dump(mode="json")])

    def enqueue_caption(self, task: CaptionTask) -> None:
        self._get_app().send_task(CAPTION_TASK, args=[task.model_dump(mode="json")])

    def healthcheck(self) -> bool:
        from kombu.exceptions import KombuError

        try:
            with self._get_app().connection_for_write() as connection:
                connection.ensure_connection(max_retries=1)
        except (KombuError, OSError) as exc:
            logger.warning("rabbitmq unreachable: {}", exc)
            return False
        return True

    def _get_app(self) -> "Celery":
        if self._app is None:
            self._app = self._make_app(self._broker_url)
        return self._app
