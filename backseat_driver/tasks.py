"""Celery tasks — the worker entry points, thin wrappers over `backseat_driver.jobs.workers`.

Start a worker with `backseat-driver worker ingest|caption`, or directly:

    celery -A backseat_driver.tasks worker -Q backseat_driver.caption --pool=solo

The solo pool runs tasks in the worker's own process: the captioning model is loaded
once (and CUDA is never forked); scale out with more worker processes or containers.
Each dependency is built on first use and cached, so importing this module costs nothing.
"""

from collections.abc import Callable
from functools import cached_property
from typing import Any, NamedTuple

from celery import Celery, Task
from celery.signals import setup_logging as celery_setup_logging
from pydantic import ValidationError

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.captioning.factory import build_captioner
from backseat_driver.config import Settings, get_settings
from backseat_driver.datasets.dataset_store import DatasetStore
from backseat_driver.datasets.factory import build_dataset_store
from backseat_driver.jobs.celery_job_queue import (
    CAPTION_TASK,
    INGEST_TASK,
    MAX_RETRIES,
    CeleryJobQueue,
    make_celery_app,
)
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore
from backseat_driver.jobs.sql_job_store import SqlJobStore
from backseat_driver.jobs.storage import JobStorage
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.logger import LogFormat, setup_logging
from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.scenes.nuscenes_scene_loader import NuScenesSceneLoader, open_nuscenes_tables
from backseat_driver.scenes.scene_loader import SceneLoader
from backseat_driver.scenes.stored_scene_loader import StoredSceneLoader


def _stored_loader(settings: Settings, dataset: DatasetStore) -> SceneLoader:
    return StoredSceneLoader(
        dataset,
        settings.nuscenes_version,
        lambda dataroot: NuScenesSceneLoader(
            dataroot=dataroot,
            version=settings.nuscenes_version,
            camera_channels=[settings.camera_channel],
            open_dataset=open_nuscenes_tables,
        ),
    )


def _postgres_store(settings: Settings) -> JobStore:
    return SqlJobStore(JobStorage(settings.database_url))


def _celery_queue(settings: Settings) -> JobQueue:
    return CeleryJobQueue(settings.rabbitmq_url)


class Workers:
    """Builds each worker (and the store they share) on first use and keeps it, so a process loads its model once."""

    def __init__(
        self,
        settings: Settings,
        build_loader: Callable[[Settings, DatasetStore], SceneLoader] = _stored_loader,
        build_queue: Callable[[Settings], JobQueue] = _celery_queue,
        build_store: Callable[[Settings], JobStore] = _postgres_store,
        build_captioner: Callable[[Settings], Captioner] = build_captioner,
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
        captioner.load()
        return CaptionWorker(captioner=captioner, store=self.store, images=self.dataset)


class Tasks(NamedTuple):
    ingest: Task
    caption: Task


# A malformed message can never succeed, so it isn't retried; anything else (database down, broker hiccup) is.
_RETRY = {"autoretry_for": (Exception,), "dont_autoretry_for": (ValidationError,), "retry_backoff": True}


def register_tasks(
    app: Celery, ingest_worker: Callable[[], IngestWorker], caption_worker: Callable[[], CaptionWorker]
) -> Tasks:
    """Register the two tasks on `app`. Workers are looked up per call, after the payload validated, so garbage
    never triggers a model or dataset load."""

    @app.task(name=INGEST_TASK, bind=True, shared=False, max_retries=MAX_RETRIES, **_RETRY)
    def ingest(self: Task, payload: dict[str, Any]) -> None:
        task = IngestTask.model_validate(payload)
        ingest_worker().handle(task)

    @app.task(name=CAPTION_TASK, bind=True, shared=False, max_retries=MAX_RETRIES, **_RETRY)
    def caption(self: Task, payload: dict[str, Any]) -> None:
        task = CaptionTask.model_validate(payload)
        caption_worker().handle(task)

    return Tasks(ingest, caption)


def configure_worker_logging(settings: Settings, setup: Callable[[LogFormat, str], None] = setup_logging) -> None:
    setup(LogFormat(settings.log_format), "worker")


_settings = get_settings()
celery_app = make_celery_app(_settings.rabbitmq_url)
workers = Workers(_settings)
ingest, caption = register_tasks(celery_app, lambda: workers.ingest_worker, lambda: workers.caption_worker)


@celery_setup_logging.connect
def _configure_logging(**_: Any) -> None:
    # Connecting to this signal stops Celery from installing its own log handlers.
    configure_worker_logging(get_settings())
