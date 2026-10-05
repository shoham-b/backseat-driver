"""Celery tasks — the worker entry points, thin wrappers over the handlers in `backseat_driver.transport`.

Start a worker with `backseat-driver worker ingest|caption`, or directly:

    celery -A backseat_driver.tasks worker -Q backseat_driver.caption --pool=solo

The solo pool runs tasks in the worker's own process: the captioning model is loaded
once (and CUDA is never forked); scale out with more worker processes or containers.
Importing this module reads the settings and builds the Celery app, which `celery -A` needs; it connects to nothing.
Every other dependency (broker, database, bucket, model) is built on first use and cached.
"""

import asyncio
from collections.abc import Callable
from functools import cached_property
from typing import Any, Literal, NamedTuple

from celery import Celery, Task
from celery.signals import setup_logging as celery_setup_logging
from loguru import logger
from pydantic import ValidationError

from backseat_driver.config import Settings, get_settings
from backseat_driver.logger import LogFormat, setup_logging
from backseat_driver.models import CaptionTask, IngestTask, JobReference
from backseat_driver.process.captioner import Captioner
from backseat_driver.process.factory import build_captioner as build_configured_captioner
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.read.s3.dataset_store import DatasetStore
from backseat_driver.read.s3.factory import build_dataset_store
from backseat_driver.stacks import celery_queue, postgres_store, stored_loader
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.celery_job_queue import CAPTION_TASK, INGEST_TASK, MAX_RETRIES, make_celery_app
from backseat_driver.transport.ingest_worker import IngestWorker
from backseat_driver.transport.job_failure import dead_letter_of, describe_failure
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.transport.job_store.job_store import JobStore


def worker_store(settings: Settings) -> JobStore:
    """A task runs its own event loop, and a pooled connection would outlive it: connect per operation instead."""
    return postgres_store(settings, pooled=False)


class Workers:
    """Builds each worker (and the store they share) on first use and keeps it, so a process loads its model once."""

    def __init__(
        self,
        settings: Settings,
        build_loader: Callable[[Settings, DatasetStore], SceneLoader] = stored_loader,
        build_queue: Callable[[Settings], JobQueue] = celery_queue,
        build_store: Callable[[Settings], JobStore] = worker_store,
        build_captioner: Callable[[Settings], Captioner] = build_configured_captioner,
        build_dataset: Callable[[Settings], DatasetStore] = build_dataset_store,
    ) -> None:
        self._settings = settings
        self._build_loader = build_loader
        self._build_queue = build_queue
        self._build_store = build_store
        self._build_captioner = build_captioner
        self._build_dataset = build_dataset

    @cached_property
    def store(self) -> JobStore:
        return self._build_store(self._settings)

    @cached_property
    def dataset(self) -> DatasetStore:
        return self._build_dataset(self._settings)

    @cached_property
    def ingest_worker(self) -> IngestWorker:
        return IngestWorker(
            loader=self._build_loader(self._settings, self.dataset),
            queue=self._build_queue(self._settings),
            store=self.store,
            images=self.dataset,
        )

    @cached_property
    def caption_worker(self) -> CaptionWorker:
        captioner = self._build_captioner(self._settings)
        asyncio.run(captioner.load())
        return CaptionWorker(captioner=captioner, store=self.store, images=self.dataset)


class Tasks(NamedTuple):
    ingest: Task
    caption: Task


# A malformed message can never succeed, so it isn't retried; anything else (database down, broker hiccup) is.
_RETRY = {"autoretry_for": (Exception,), "dont_autoretry_for": (ValidationError,), "retry_backoff": True}


def register_tasks(
    app: Celery,
    ingest_worker: Callable[[], IngestWorker],
    caption_worker: Callable[[], CaptionWorker],
    store: Callable[[], JobStore],
) -> Tasks:
    """Register the two tasks on `app`. Workers are looked up per call, after the payload validated, so garbage
    never triggers a model or dataset load. A task that gives up marks its job failed in `store`."""

    class FailJobWhenGivingUp(Task):
        def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
            # Celery calls this only once retries are exhausted, so a transient error that a retry fixes never
            # marks a job failed.
            kind = "ingest" if self.name == INGEST_TASK else "caption"
            asyncio.run(_give_up(store(), str(self.name), task_id, kind, args[0], exc))

    @app.task(name=INGEST_TASK, base=FailJobWhenGivingUp, bind=True, shared=False, max_retries=MAX_RETRIES, **_RETRY)
    def ingest(self: Task, payload: dict[str, Any]) -> None:
        task = IngestTask.model_validate(payload)
        asyncio.run(ingest_worker().handle(task))

    @app.task(name=CAPTION_TASK, base=FailJobWhenGivingUp, bind=True, shared=False, max_retries=MAX_RETRIES, **_RETRY)
    def caption(self: Task, payload: dict[str, Any]) -> None:
        task = CaptionTask.model_validate(payload)
        asyncio.run(caption_worker().handle(task))

    return Tasks(ingest, caption)


async def _give_up(
    job_store: JobStore,
    task_name: str,
    task_id: str,
    kind: Literal["ingest", "caption"],
    payload: Any,
    error: Exception,
) -> None:
    """Record a task that ran out of retries: fail its job and keep the payload as a dead letter."""
    try:
        reference = JobReference.model_validate(payload)
    except ValidationError:
        # No job to mark failed, but the message is kept so it isn't lost without a trace.
        logger.error("{} {} failed and its payload names no job: {}", task_name, task_id, error)
        raw = payload if isinstance(payload, dict) else {"raw": repr(payload)}
        await job_store.record_dead_letter(None, dead_letter_of(kind, raw, error))
        return
    await job_store.fail_job(reference.job_id, describe_failure(task_name, error))
    await job_store.record_dead_letter(reference.job_id, dead_letter_of(kind, payload, error))


def configure_worker_logging(settings: Settings, setup: Callable[[LogFormat, str], None] = setup_logging) -> None:
    setup(LogFormat(settings.log_format), "worker")


_settings = get_settings()
celery_app = make_celery_app(_settings.rabbitmq_url)
workers = Workers(_settings)
ingest, caption = register_tasks(
    celery_app, lambda: workers.ingest_worker, lambda: workers.caption_worker, lambda: workers.store
)


@celery_setup_logging.connect
def _configure_logging(**_: Any) -> None:
    # Connecting to this signal stops Celery from installing its own log handlers.
    configure_worker_logging(get_settings())
