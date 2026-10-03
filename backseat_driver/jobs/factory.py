"""Builds the configured `JobQueue` and `JobStore` so the API picks a run mode from one place."""

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.config import RunMode, Settings
from backseat_driver.jobs.celery_job_queue import CeleryJobQueue
from backseat_driver.jobs.in_memory_job_store import InMemoryJobStore
from backseat_driver.jobs.in_process_job_queue import InProcessJobQueue
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore
from backseat_driver.jobs.postgres_job_store import PostgresJobStore
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.scenes.nuscenes_scene_loader import NuScenesSceneLoader


def build_job_backend(settings: Settings, captioner: Captioner) -> tuple[JobQueue, JobStore]:
    """Return the queue and store for `settings.mode`.

    Distributed: Celery/RabbitMQ and Postgres, consumed by the separate worker services.
    Monolith: an in-process queue and in-memory store, where the API process runs the same worker
    handlers itself and shares its own `captioner` with them.
    """
    if settings.mode is RunMode.DISTRIBUTED:
        return CeleryJobQueue(settings.rabbitmq_url), PostgresJobStore(settings.database_url)

    queue, store = InProcessJobQueue(), InMemoryJobStore()
    loader = NuScenesSceneLoader(
        dataroot=settings.nuscenes_dataroot,
        version=settings.nuscenes_version,
        camera_channels=[settings.camera_channel],
    )
    queue.register(
        on_ingest=IngestWorker(loader=loader, queue=queue, store=store).handle,
        on_caption=CaptionWorker(captioner=captioner, store=store).handle,
    )
    return queue, store
