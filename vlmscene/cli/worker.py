"""Queue workers for the distributed mode — long-running consumers, one per queue.

Usage::

    vlm-scene-description worker ingest
    vlm-scene-description worker caption
"""

from vlmscene.cli import worker_app
from vlmscene.config import get_settings
from vlmscene.logger import LogFormat, setup_logging


@worker_app.command()
def ingest() -> None:
    """Consume ingest tasks: load the dataset and fan out one caption task per scene."""
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="ingest-worker")

    from loguru import logger

    from vlmscene.bl.job_queue import INGEST_QUEUE, RabbitMQJobQueue
    from vlmscene.bl.job_store import PostgresJobStore
    from vlmscene.bl.nuscenes_loader import NuScenesSceneLoader
    from vlmscene.bl.workers import IngestWorker

    queue = RabbitMQJobQueue(settings.rabbitmq_url)
    loader = NuScenesSceneLoader(
        dataroot=settings.nuscenes_dataroot,
        version=settings.nuscenes_version,
        camera_channel=settings.camera_channel,
    )
    worker = IngestWorker(loader=loader, queue=queue, store=PostgresJobStore(settings.database_url))

    logger.bind(queue=INGEST_QUEUE).info("ingest worker started")
    queue.consume(INGEST_QUEUE, worker.handle, prefetch=1)


@worker_app.command()
def caption() -> None:
    """Consume caption tasks: run each scene's keyframe through the VLM and record the result."""
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="caption-worker")

    from loguru import logger

    from vlmscene.bl.captioner import BlipCaptioner
    from vlmscene.bl.job_queue import CAPTION_QUEUE, RabbitMQJobQueue
    from vlmscene.bl.job_store import PostgresJobStore
    from vlmscene.bl.workers import CaptionWorker

    captioner = BlipCaptioner(model_name=settings.vlm_model_name)
    # Load before consuming, not on the first message: a model that can't load should fail
    # the worker at startup, not leave it pulling messages it would fail every time.
    captioner.load()
    worker = CaptionWorker(captioner=captioner, store=PostgresJobStore(settings.database_url))
    queue = RabbitMQJobQueue(settings.rabbitmq_url)

    logger.bind(queue=CAPTION_QUEUE, model=captioner.model_name).info("caption worker started")
    queue.consume(CAPTION_QUEUE, worker.handle, prefetch=settings.caption_prefetch)
