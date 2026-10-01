"""Celery tasks — the worker entry points, thin wrappers over `vlmscene.bl.workers`.

Start a worker with `vlm-scene-description worker ingest|caption`, or directly:

    celery -A vlmscene.tasks worker -Q vlmscene.caption --pool=solo

The solo pool runs tasks in the worker's own process: the captioning model is loaded
once (and CUDA is never forked); scale out with more worker processes or containers.
Each dependency is built on first use and cached, so importing this module costs nothing.
"""

from functools import cache
from typing import Any

from celery import Task
from celery.signals import setup_logging as celery_setup_logging
from pydantic import ValidationError

from vlmscene.bl.captioner import BlipCaptioner
from vlmscene.bl.job_queue import CAPTION_TASK, INGEST_TASK, MAX_RETRIES, CeleryJobQueue, make_celery_app
from vlmscene.bl.job_store import PostgresJobStore
from vlmscene.bl.nuscenes_loader import NuScenesSceneLoader
from vlmscene.bl.workers import CaptionWorker, IngestWorker
from vlmscene.config import get_settings
from vlmscene.logger import LogFormat, setup_logging
from vlmscene.models import CaptionTask, IngestTask

celery_app = make_celery_app(get_settings().rabbitmq_url)


@celery_setup_logging.connect
def _configure_logging(**_: Any) -> None:
    # Connecting to this signal stops Celery from installing its own log handlers.
    setup_logging(LogFormat(get_settings().log_format), service="worker")


@cache
def _store() -> PostgresJobStore:
    return PostgresJobStore(get_settings().database_url)


@cache
def ingest_worker() -> IngestWorker:
    settings = get_settings()
    loader = NuScenesSceneLoader(
        dataroot=settings.nuscenes_dataroot,
        version=settings.nuscenes_version,
        camera_channel=settings.camera_channel,
    )
    return IngestWorker(loader=loader, queue=CeleryJobQueue(settings.rabbitmq_url), store=_store())


@cache
def caption_worker() -> CaptionWorker:
    captioner = BlipCaptioner(model_name=get_settings().vlm_model_name)
    captioner.load()
    return CaptionWorker(captioner=captioner, store=_store())


# A malformed message can never succeed, so it isn't retried; anything else (database down, broker hiccup) is.
_RETRY = {"autoretry_for": (Exception,), "dont_autoretry_for": (ValidationError,), "retry_backoff": True}


@celery_app.task(name=INGEST_TASK, bind=True, max_retries=MAX_RETRIES, **_RETRY)
def ingest(self: Task, payload: dict[str, Any]) -> None:
    task = IngestTask.model_validate(
        payload
    )  # before building the worker, so garbage never triggers a model or dataset load
    ingest_worker().handle(task)


@celery_app.task(name=CAPTION_TASK, bind=True, max_retries=MAX_RETRIES, **_RETRY)
def caption(self: Task, payload: dict[str, Any]) -> None:
    task = CaptionTask.model_validate(payload)
    caption_worker().handle(task)
