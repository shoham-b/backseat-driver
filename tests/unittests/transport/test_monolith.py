"""Monolith mode: the in-process queue and in-memory store that replace RabbitMQ and Postgres."""

import threading
import time
from uuid import uuid4

import pytest

from backseat_driver.config import RunMode, Settings
from backseat_driver.errors import NotFoundError
from backseat_driver.models import CaptionTask, IngestTask, JobState
from backseat_driver.pipeline import describe_keyframe
from backseat_driver.stacks import build_job_backend
from backseat_driver.transport.celery_job_queue import CeleryJobQueue
from backseat_driver.transport.in_process_job_queue import InProcessJobQueue
from backseat_driver.write.job_store.in_memory_job_store import InMemoryJobStore
from backseat_driver.write.job_store.sql_job_store import SqlJobStore
from tests.fakes import FakeCaptioner, FakeImageStore, FakeSceneLoader, make_image_uri, make_keyframe


def test_mode_defaults_to_monolith() -> None:
    assert Settings(_env_file=None).mode is RunMode.MONOLITH


def test_distributed_mode_builds_celery_and_postgres() -> None:
    settings = Settings(_env_file=None, mode=RunMode.DISTRIBUTED, dataset_bucket="nuscenes")

    queue, store = build_job_backend(settings, FakeCaptioner(), FakeImageStore())

    assert isinstance(queue, CeleryJobQueue)
    assert isinstance(store, SqlJobStore)


def test_monolith_keeps_jobs_in_memory_when_no_database_file_is_configured() -> None:
    _, store = build_job_backend(
        Settings(_env_file=None, mode=RunMode.MONOLITH, jobs_db_path=""), FakeCaptioner(), FakeImageStore()
    )

    assert isinstance(store, InMemoryJobStore)


def test_monolith_job_runs_to_completion_without_a_broker() -> None:
    keyframes = [make_keyframe(1), make_keyframe(2)]
    queue, store = build_job_backend(
        Settings(_env_file=None, mode=RunMode.MONOLITH, jobs_db_path=""),
        FakeCaptioner(),
        FakeImageStore(),
        build_loader=lambda settings: FakeSceneLoader(keyframes),
    )
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="tx"))

    deadline = time.monotonic() + 5
    while store.get_job(job_id).state is not JobState.COMPLETED and time.monotonic() < deadline:
        time.sleep(0.01)

    assert [d.scene_name for d in store.list_descriptions(job_id)] == ["scene-0001", "scene-0002"]


def test_listing_jobs_returns_the_newest_first() -> None:
    store, first, second = InMemoryJobStore(), uuid4(), uuid4()
    store.create_job(first, None, "tx-1")
    store.create_job(second, None, "tx-2")

    jobs = store.list_jobs()

    assert [job.job_id for job in jobs] == [second, first]


def test_queue_runs_tasks_in_order_on_one_background_thread() -> None:
    queue = InProcessJobQueue()
    seen: list[tuple[str, str]] = []
    done = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        seen.append(("ingest", threading.current_thread().name))

    def on_caption(task: CaptionTask) -> None:
        seen.append(("caption", threading.current_thread().name))
        done.set()

    queue.register(on_ingest, on_caption, on_failure=lambda task, error: None)

    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="tx"))
    queue.enqueue_caption(
        CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))
    )

    assert done.wait(timeout=5)
    assert seen == [("ingest", "in-process-worker"), ("caption", "in-process-worker")]


def test_failing_task_does_not_stop_later_tasks() -> None:
    queue = InProcessJobQueue()
    done = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    queue.register(on_ingest, lambda task: done.set(), on_failure=lambda task, error: None)

    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="tx"))
    queue.enqueue_caption(
        CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))
    )

    assert done.wait(timeout=5)


def test_failing_task_is_reported_with_its_error() -> None:
    queue = InProcessJobQueue()
    reported: list[tuple[IngestTask | CaptionTask, Exception]] = []
    done = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    def on_failure(task: IngestTask | CaptionTask, error: Exception) -> None:
        reported.append((task, error))
        done.set()

    queue.register(on_ingest, lambda task: None, on_failure=on_failure)
    task = IngestTask(job_id=uuid4(), transaction_id="tx")

    queue.enqueue_ingest(task)

    assert done.wait(timeout=5)
    assert [(t, str(e)) for t, e in reported] == [(task, "boom")]


def test_a_failure_that_cannot_be_recorded_does_not_stop_later_tasks() -> None:
    queue = InProcessJobQueue()
    done = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    def on_failure(task: IngestTask | CaptionTask, error: Exception) -> None:
        raise ConnectionError("store down")

    queue.register(on_ingest, lambda task: done.set(), on_failure=on_failure)

    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="tx"))
    queue.enqueue_caption(
        CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))
    )

    assert done.wait(timeout=5)


def test_enqueue_before_register_fails_fast() -> None:
    queue = InProcessJobQueue()

    with pytest.raises(RuntimeError, match="register"):
        queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="tx"))
    with pytest.raises(RuntimeError, match="register"):
        queue.enqueue_caption(
            CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))
        )


def test_queue_is_healthy_and_starts_no_thread_until_used() -> None:
    queue = InProcessJobQueue()

    assert queue.healthcheck() is True
    assert queue._thread is None


def test_store_tracks_progress_and_is_idempotent() -> None:
    store, job_id = InMemoryJobStore(), uuid4()
    store.create_job(job_id, 2, "tx")
    assert store.get_job(job_id).state is JobState.PENDING

    store.set_expected_scenes(job_id, 1)
    assert store.get_job(job_id).state is JobState.RUNNING

    description = _description(1)
    store.record_description(job_id, description)
    store.record_description(job_id, description)

    job = store.get_job(job_id)
    assert (job.state, job.completed_scenes, job.max_scenes, job.transaction_id) == (JobState.COMPLETED, 1, 2, "tx")
    assert store.list_descriptions(job_id) == [description]
    assert store.healthcheck() is True


def test_store_raises_not_found_for_unknown_job() -> None:
    store, job_id = InMemoryJobStore(), uuid4()

    for call in (
        lambda: store.get_job(job_id),
        lambda: store.list_descriptions(job_id),
        lambda: store.set_expected_scenes(job_id, 1),
        lambda: store.record_description(job_id, _description(1)),
    ):
        with pytest.raises(NotFoundError):
            call()


def _description(n: int):

    return describe_keyframe(make_keyframe(n), FakeCaptioner(), make_keyframe(n).image_path)
