from collections.abc import Iterator
from unittest import mock
from uuid import uuid4

import pytest
from celery import Task
from pydantic import ValidationError

from backseat_driver import tasks
from backseat_driver.jobs.celery_job_queue import MAX_RETRIES
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.config import get_settings
from backseat_driver.logger import LogFormat
from backseat_driver.models import CaptionTask, IngestTask
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe


def test_caption_task_validates_the_payload_and_hands_it_to_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    monkeypatch.setattr(tasks, "caption_worker", lambda: CaptionWorker(FakeCaptioner(), store))
    payload = CaptionTask(job_id=job_id, transaction_id="tx-1", keyframe=make_keyframe(1)).model_dump(mode="json")

    tasks.caption.apply(args=[payload]).get()

    assert store.get_job(job_id).completed_scenes == 1


def test_malformed_payload_fails_without_being_retried() -> None:
    result = tasks.caption.apply(args=[{"not": "a caption task"}])

    assert isinstance(result.result, ValidationError)
    assert result.traceback is not None
    assert result.state == "FAILURE"


def test_tasks_are_registered_under_the_names_the_api_publishes_to() -> None:
    assert {"backseat_driver.ingest", "backseat_driver.caption"} <= set(tasks.celery_app.tasks)


@pytest.fixture(autouse=True)
def _fresh_dependency_caches() -> Iterator[None]:
    for cached in (tasks._store, tasks.ingest_worker, tasks.caption_worker):
        cached.cache_clear()
    yield
    for cached in (tasks._store, tasks.ingest_worker, tasks.caption_worker):
        cached.cache_clear()


def test_ingest_task_validates_the_payload_and_fans_out_through_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, store, queue = uuid4(), FakeJobStore(), FakeJobQueue()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)
    monkeypatch.setattr(tasks, "ingest_worker", lambda: worker)
    payload = IngestTask(job_id=job_id, transaction_id="tx-1").model_dump(mode="json")

    tasks.ingest.apply(args=[payload]).get()

    assert store.get_job(job_id).expected_scenes == 2
    assert len(queue.caption_tasks) == 2


def test_malformed_ingest_payload_never_builds_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    build = mock.Mock()
    monkeypatch.setattr(tasks, "ingest_worker", build)

    result = tasks.ingest.apply(args=[{"job_id": "not-a-uuid"}])

    assert isinstance(result.result, ValidationError)
    build.assert_not_called()


def test_malformed_caption_payload_never_builds_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    build = mock.Mock()
    monkeypatch.setattr(tasks, "caption_worker", build)

    tasks.caption.apply(args=[{}])

    build.assert_not_called()


@pytest.mark.parametrize("task", [tasks.ingest, tasks.caption])
def test_transient_failures_are_retried_up_to_the_limit_then_surface(
    monkeypatch: pytest.MonkeyPatch, task: Task
) -> None:
    worker = mock.Mock()
    worker.handle.side_effect = ConnectionError("database down")
    monkeypatch.setattr(tasks, "ingest_worker", lambda: worker)
    monkeypatch.setattr(tasks, "caption_worker", lambda: worker)
    payload = {
        tasks.ingest: IngestTask(job_id=uuid4(), transaction_id="tx").model_dump(mode="json"),
        tasks.caption: CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1)).model_dump(
            mode="json"
        ),
    }[task]

    result = task.apply(args=[payload])

    assert isinstance(result.result, ConnectionError)
    assert worker.handle.call_count == MAX_RETRIES + 1


def test_tasks_declare_the_shared_retry_limit() -> None:
    assert tasks.ingest.max_retries == MAX_RETRIES
    assert tasks.caption.max_retries == MAX_RETRIES


def test_ingest_worker_is_built_from_settings_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    loader_cls, queue_cls, store_cls = mock.Mock(), mock.Mock(), mock.Mock()
    monkeypatch.setattr(tasks, "NuScenesSceneLoader", loader_cls)
    monkeypatch.setattr(tasks, "CeleryJobQueue", queue_cls)
    monkeypatch.setattr(tasks, "PostgresJobStore", store_cls)
    monkeypatch.setenv("BACKSEAT_DRIVER_NUSCENES_DATAROOT", "/data/nu")
    monkeypatch.setenv("BACKSEAT_DRIVER_NUSCENES_VERSION", "v1.0-trainval")
    monkeypatch.setenv("BACKSEAT_DRIVER_CAMERA_CHANNEL", "CAM_BACK")
    monkeypatch.setenv("BACKSEAT_DRIVER_RABBITMQ_URL", "amqp://broker/")
    monkeypatch.setenv("BACKSEAT_DRIVER_DATABASE_URL", "postgresql+psycopg://db/x")
    get_settings.cache_clear()

    first = tasks.ingest_worker()
    second = tasks.ingest_worker()
    get_settings.cache_clear()

    assert first is second
    loader_cls.assert_called_once_with(dataroot="/data/nu", version="v1.0-trainval", camera_channel="CAM_BACK")
    queue_cls.assert_called_once_with("amqp://broker/")
    store_cls.assert_called_once_with("postgresql+psycopg://db/x")


def test_caption_worker_loads_the_model_once_and_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    captioner = mock.Mock()
    monkeypatch.setattr(tasks, "build_captioner", lambda settings: captioner)
    monkeypatch.setattr(tasks, "PostgresJobStore", mock.Mock())

    first = tasks.caption_worker()
    second = tasks.caption_worker()

    assert first is second
    captioner.load.assert_called_once_with()


def test_store_is_shared_between_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    store_cls = mock.Mock()
    monkeypatch.setattr(tasks, "PostgresJobStore", store_cls)
    monkeypatch.setattr(tasks, "build_captioner", lambda settings: mock.Mock())
    monkeypatch.setattr(tasks, "NuScenesSceneLoader", mock.Mock())
    monkeypatch.setattr(tasks, "CeleryJobQueue", mock.Mock())

    tasks.ingest_worker()
    tasks.caption_worker()

    store_cls.assert_called_once()


def test_celery_logging_hook_installs_service_tagged_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = mock.Mock()
    monkeypatch.setattr(tasks, "setup_logging", setup)

    tasks._configure_logging()

    setup.assert_called_once_with(LogFormat.COLORED, service="worker")
