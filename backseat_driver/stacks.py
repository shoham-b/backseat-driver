"""Which implementation each rung plugs into each port: the one place the whole wiring can be read.

See docs/ladder.md for the diagrams. Every function here is a recipe that builds real collaborators and nothing
else, and none connects to anything until it is used.

    port                rung 1: pipeline        rung 2: seam               rung 3: machines
    ------------------  ----------------------  -------------------------  ---------------------------
    read   SceneLoader  NuScenesSceneLoader     RelativeSceneLoader        StoredSceneLoader (bucket)
    read   ImageStore   LocalImageStore         LocalImageStore            S3DatasetStore
    hand-off JobQueue   (a function call)       InProcessJobQueue          CeleryJobQueue (RabbitMQ)
    process Captioner   BackendCaptioner        BackendCaptioner           BackendCaptioner
    write  JobStore     (write_json)            SqlJobStore, SQLite        SqlJobStore, Postgres

The captioner is the same at every rung, so it is built by `process.factory.build_captioner` wherever it is needed.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

from backseat_driver.config import RunMode, Settings, VlmBackend
from backseat_driver.models import IngestTask
from backseat_driver.pipeline import ScenePipeline
from backseat_driver.process.captioner import Captioner
from backseat_driver.process.factory import build_captioner
from backseat_driver.read.image_store import ImageStore
from backseat_driver.read.local_image_store import LocalImageStore
from backseat_driver.read.nuscenes_scene_loader import NuScenesSceneLoader, open_nuscenes_tables
from backseat_driver.read.relative_scene_loader import RelativeSceneLoader
from backseat_driver.read.s3.dataset_store import DatasetStore
from backseat_driver.read.s3.factory import build_dataset_store
from backseat_driver.read.s3.stored_scene_loader import StoredSceneLoader
from backseat_driver.read.scene_loader import SceneLoader
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.celery_job_queue import CeleryJobQueue
from backseat_driver.transport.in_process_job_queue import InProcessJobQueue
from backseat_driver.transport.ingest_worker import IngestWorker
from backseat_driver.transport.job_failure import describe_failure
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.write.job_store.in_memory_job_store import InMemoryJobStore
from backseat_driver.write.job_store.job_store import JobStore
from backseat_driver.write.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.storage import JobStorage

# Rung 1: the pipeline. One process, one function call, no queue and no job store.


def pipeline(
    settings: Settings,
    dataroot: str,
    version: str,
    cameras: Sequence[str],
    backend: VlmBackend | None = None,
    model: str | None = None,
) -> ScenePipeline:
    loader = NuScenesSceneLoader(dataroot=dataroot, version=version, camera_channels=cameras)
    captioner = build_captioner(settings, backend=backend, model_name=model)
    return ScenePipeline(loader=loader, captioner=captioner)


# Rung 2: the seam. The same steps as tasks, both ends of the queue in the API process on one thread.


def seam(
    settings: Settings,
    captioner: Captioner,
    images: ImageStore,
    build_loader: Callable[[Settings], SceneLoader],
) -> tuple[JobQueue, JobStore]:
    queue, store = InProcessJobQueue(), _sqlite_or_memory_store(settings)
    queue.register(
        on_ingest=IngestWorker(loader=build_loader(settings), queue=queue, store=store, images=images).handle,
        on_caption=CaptionWorker(captioner=captioner, store=store, images=images).handle,
        on_failure=lambda task, error: store.fail_job(
            task.job_id, describe_failure("ingest" if isinstance(task, IngestTask) else "caption", error)
        ),
    )
    return queue, store


def nuscenes_loader(settings: Settings) -> SceneLoader:
    return RelativeSceneLoader(
        NuScenesSceneLoader(
            dataroot=settings.nuscenes_dataroot,
            version=settings.nuscenes_version,
            camera_channels=[settings.camera_channel],
        ),
        settings.nuscenes_dataroot,
    )


def _sqlite_or_memory_store(settings: Settings) -> JobStore:
    if not settings.jobs_db_path:
        return InMemoryJobStore()
    path = Path(settings.jobs_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SqlJobStore(JobStorage(f"sqlite:///{path.as_posix()}"))
    store.ensure_schema()
    return store


# Rung 3: machines. The API only enqueues and reads; the workers (`tasks.Workers`) build their own ends from the
# same pieces below, so neither side shares a disk or a process with the other.


def machines(settings: Settings) -> tuple[JobQueue, JobStore]:
    return celery_queue(settings), postgres_store(settings)


def celery_queue(settings: Settings) -> JobQueue:
    return CeleryJobQueue(settings.rabbitmq_url)


def postgres_store(settings: Settings) -> JobStore:
    return SqlJobStore(JobStorage(settings.database_url))


def stored_loader(settings: Settings, dataset: DatasetStore) -> SceneLoader:
    """Ingest's loader: the devkit over only the metadata tables, downloaded from the bucket."""
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


# What the API and the workers call: pick the rung from `settings.mode`.


def build_image_store(settings: Settings) -> ImageStore:
    """Where image bytes come from: the local dataroot in the monolith, the bucket once workers share no disk."""
    if settings.mode is RunMode.MONOLITH:
        return LocalImageStore(settings.nuscenes_dataroot)
    return build_dataset_store(settings)


def build_job_backend(
    settings: Settings,
    captioner: Captioner,
    images: ImageStore,
    build_loader: Callable[[Settings], SceneLoader] = nuscenes_loader,
) -> tuple[JobQueue, JobStore]:
    """The queue and job store the API uses for `/jobs`: rung 2 in the monolith, rung 3 when distributed."""
    if settings.mode is RunMode.DISTRIBUTED:
        return machines(settings)
    return seam(settings, captioner, images, build_loader)
