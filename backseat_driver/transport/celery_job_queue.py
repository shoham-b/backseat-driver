"""Celery/RabbitMQ adapter for the `JobQueue` port.

Celery runs the workers (`backseat_driver.tasks`); this module is the producing side and
the shared broker configuration. Tasks are addressed by name, so the API can enqueue
work without importing the worker code (and therefore without torch or nuscenes-devkit).
Celery is imported lazily, so unit tests and the batch CLI never need it.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.job_queue import JobQueue

if TYPE_CHECKING:
    from celery import Celery

INGEST_QUEUE = "backseat_driver.ingest"
CAPTION_QUEUE = "backseat_driver.caption"
INGEST_TASK = "backseat_driver.ingest"
CAPTION_TASK = "backseat_driver.caption"

# After this many retries a failing task is given up on and logged; it is not redelivered forever.
MAX_RETRIES = 3


def make_celery_app(broker_url: str) -> "Celery":
    """Build the Celery app shared by producers and workers, so both agree on queues and delivery guarantees."""
    from celery import Celery
    from kombu import Queue

    app = Celery("backseat_driver", broker=broker_url)
    app.conf.update(
        # Quorum queues are replicated and durable, the recommended RabbitMQ queue type for work that must not be lost.
        task_queues=[
            Queue(name, routing_key=name, queue_arguments={"x-queue-type": "quorum"})
            for name in (INGEST_QUEUE, CAPTION_QUEUE)
        ],
        task_routes={INGEST_TASK: {"queue": INGEST_QUEUE}, CAPTION_TASK: {"queue": CAPTION_QUEUE}},
        # Results live in Postgres (the job store), so Celery keeps none.
        task_ignore_result=True,
        # Ack after the work is recorded, and take one message at a time so a slow caption doesn't hoard the queue.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_transport_options={"confirm_publish": True},  # publishing raises instead of silently losing a message
        broker_connection_retry_on_startup=True,
        # RabbitMQ 4 rejects the transient, non-exclusive queues Celery uses for remote control and gossip
        # (the deprecated `transient_nonexcl_queues` feature), and nothing here needs them.
        worker_enable_remote_control=False,
    )
    return app


class CeleryJobQueue(JobQueue):
    """`JobQueue` that publishes to RabbitMQ through Celery. Constructing it never connects."""

    def __init__(self, broker_url: str, make_app: Callable[[str], Any] = make_celery_app) -> None:
        self._broker_url = broker_url
        self._make_app = make_app
        self._app: Celery | None = None

    # Celery has no asynchronous producer: publishing connects, writes and waits for the broker's confirmation, so each
    # call runs on a worker thread and leaves the event loop free.

    async def enqueue_ingest(self, task: IngestTask) -> None:
        await asyncio.to_thread(self._send, INGEST_TASK, task.model_dump(mode="json"))

    async def enqueue_caption(self, task: CaptionTask) -> None:
        await asyncio.to_thread(self._send, CAPTION_TASK, task.model_dump(mode="json"))

    async def healthcheck(self) -> bool:
        return await asyncio.to_thread(self._healthcheck)

    def _send(self, task_name: str, payload: dict[str, Any]) -> None:
        self._get_app().send_task(task_name, args=[payload])

    def _healthcheck(self) -> bool:
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
