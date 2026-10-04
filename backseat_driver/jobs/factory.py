"""Builds the configured `JobQueue` and `JobStore` so the API picks a run mode from one place."""

from collections.abc import Callable
from pathlib import Path

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.config import RunMode, Settings
from backseat_driver.jobs.celery_job_queue import CeleryJobQueue
from backseat_driver.jobs.in_memory_job_store import InMemoryJobStore
from backseat_driver.jobs.in_process_job_queue import InProcessJobQueue
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore
from backseat_driver.jobs.sql_job_store import SqlJobStore
from backseat_driver.jobs.storage import JobStorage
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.scenes.nuscenes_scene_loader import NuScenesSceneLoader
from backseat_driver.scenes.scene_loader import SceneLoader


def nuscenes_loader(settings: Settings) -> SceneLoader:
    return NuScenesSceneLoader(
        dataroot=settings.nuscenes_dataroot,
        version=settings.nuscenes_version,
        camera_channels=[settings.camera_channel],
    )


def build_job_backend(
    settings: Settings, captioner: Captioner, build_loader: Callable[[Settings], SceneLoader] = nuscenes_loader
) -> tuple[JobQueue, JobStore]:
    """Return the queue and store for `settings.mode`.

    Distributed: Celery/RabbitMQ and Postgres, consumed by the separate worker services.
    Monolith: an in-process queue and a SQLite job store (in memory when `jobs_db_path` is empty), where the API
    process runs the same worker handlers itself and shares its own `captioner` with them.
    """
    if settings.mode is RunMode.DISTRIBUTED:
        return CeleryJobQueue(settings.rabbitmq_url), SqlJobStore(JobStorage(settings.database_url))

    queue, store = InProcessJobQueue(), _monolith_store(settings)
    queue.register(
        on_ingest=IngestWorker(loader=build_loader(settings), queue=queue, store=store).handle,
        on_caption=CaptionWorker(captioner=captioner, store=store).handle,
    )
    return queue, store


def _monolith_store(settings: Settings) -> JobStore:
    if not settings.jobs_db_path:
        return InMemoryJobStore()
    path = Path(settings.jobs_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SqlJobStore(JobStorage(f"sqlite:///{path.as_posix()}"))
    store.ensure_schema()
    return store
