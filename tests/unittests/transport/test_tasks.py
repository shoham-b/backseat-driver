from collections.abc import Callable
from uuid import uuid4

from pydantic import ValidationError

from backseat_driver import tasks
from backseat_driver.config import Settings
from backseat_driver.logger import LogFormat
from backseat_driver.models import CaptionTask, IngestTask, JobState
from backseat_driver.process.captioner import Captioner
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.read.s3.dataset_store import DatasetStore
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.celery_job_queue import MAX_RETRIES, make_celery_app
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.fakes import (
    FakeCaptioner,
    FakeDatasetStore,
    FakeImageStore,
    FakeJobQueue,
    FakeJobStore,
    FakeSceneLoader,
    make_image_uri,
    make_keyframe,
    make_settings,
)


class _FailingIngestWorker(IngestWorker):
    def __init__(self) -> None:
        super().__init__(FakeSceneLoader([]), FakeJobQueue(), FakeJobStore(), FakeImageStore())
        self.calls = 0

    def handle(self, task: IngestTask) -> None:
        self.calls += 1
        raise ConnectionError("database down")


class _FailingCaptionWorker(CaptionWorker):
    def __init__(self) -> None:
        super().__init__(FakeCaptioner(), FakeJobStore(), FakeImageStore())
        self.calls = 0

    def handle(self, task: CaptionTask) -> None:
        self.calls += 1
        raise ConnectionError("database down")


class _WorkerProvider[W]:
    """Hands out `worker` and counts how often a task asked for it."""

    def __init__(self, worker: W) -> None:
        self.worker = worker
        self.requests = 0

    def __call__(self) -> W:
        self.requests += 1
        return self.worker


def _register(
    ingest_worker: Callable[[], IngestWorker] | None = None,
    caption_worker: Callable[[], CaptionWorker] | None = None,
    store: FakeJobStore | None = None,
) -> tasks.Tasks:
    """The two tasks on a throwaway app, so each test wires its own workers."""
    ingest_worker = ingest_worker or _WorkerProvider(_FailingIngestWorker())
    caption_worker = caption_worker or _WorkerProvider(_FailingCaptionWorker())
    job_store = store or FakeJobStore()
    return tasks.register_tasks(make_celery_app("memory://"), ingest_worker, caption_worker, lambda: job_store)


def test_caption_task_validates_the_payload_and_hands_it_to_the_worker() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    registered = _register(caption_worker=_WorkerProvider(CaptionWorker(FakeCaptioner(), store, FakeImageStore())))
    payload = CaptionTask(
        job_id=job_id, transaction_id="tx-1", keyframe=make_keyframe(1), image_uri=make_image_uri(1)
    ).model_dump(mode="json")

    registered.caption.apply(args=[payload]).get()

    assert store.get_job(job_id).completed_scenes == 1


def test_malformed_payload_fails_without_being_retried() -> None:
    result = _register().caption.apply(args=[{"not": "a caption task"}])

    assert isinstance(result.result, ValidationError)
    assert result.traceback is not None
    assert result.state == "FAILURE"


def test_tasks_are_registered_under_the_names_the_api_publishes_to() -> None:
    assert {"backseat_driver.ingest", "backseat_driver.caption"} <= set(tasks.celery_app.tasks)


def test_ingest_task_validates_the_payload_and_fans_out_through_the_worker() -> None:
    job_id, store, queue = uuid4(), FakeJobStore(), FakeJobQueue()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())
    registered = _register(ingest_worker=_WorkerProvider(worker))
    payload = IngestTask(job_id=job_id, transaction_id="tx-1").model_dump(mode="json")

    registered.ingest.apply(args=[payload]).get()

    assert store.get_job(job_id).expected_scenes == 2
    assert len(queue.caption_tasks) == 2


def test_malformed_ingest_payload_never_asks_for_the_worker() -> None:
    provider = _WorkerProvider(_FailingIngestWorker())

    result = _register(ingest_worker=provider).ingest.apply(args=[{"job_id": "not-a-uuid"}])

    assert isinstance(result.result, ValidationError)
    assert provider.requests == 0


def test_malformed_caption_payload_never_asks_for_the_worker() -> None:
    provider = _WorkerProvider(_FailingCaptionWorker())

    _register(caption_worker=provider).caption.apply(args=[{}])

    assert provider.requests == 0


def test_transient_ingest_failures_are_retried_up_to_the_limit_then_surface() -> None:
    worker, job_id, store = _FailingIngestWorker(), uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    payload = IngestTask(job_id=job_id, transaction_id="tx").model_dump(mode="json")

    result = _register(ingest_worker=_WorkerProvider(worker), store=store).ingest.apply(args=[payload])

    assert isinstance(result.result, ConnectionError)
    assert worker.calls == MAX_RETRIES + 1


def test_transient_caption_failures_are_retried_up_to_the_limit_then_surface() -> None:
    worker, job_id, store = _FailingCaptionWorker(), uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    payload = CaptionTask(
        job_id=job_id, transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1)
    ).model_dump(mode="json")

    result = _register(caption_worker=_WorkerProvider(worker), store=store).caption.apply(args=[payload])

    assert isinstance(result.result, ConnectionError)
    assert worker.calls == MAX_RETRIES + 1


def test_ingest_task_that_gives_up_marks_its_job_failed() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    payload = IngestTask(job_id=job_id, transaction_id="tx").model_dump(mode="json")

    _register(store=store).ingest.apply(args=[payload])

    job = store.get_job(job_id)
    assert job.state is JobState.FAILED
    assert job.error == "backseat_driver.ingest failed: ConnectionError: database down"


def test_caption_task_that_gives_up_marks_its_job_failed() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    payload = CaptionTask(
        job_id=job_id, transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1)
    ).model_dump(mode="json")

    _register(store=store).caption.apply(args=[payload])

    assert store.get_job(job_id).state is JobState.FAILED


def test_a_failed_task_whose_payload_names_no_job_leaves_the_store_alone() -> None:
    store = FakeJobStore()

    _register(store=store).caption.apply(args=[{"not": "a caption task"}])

    assert store.list_jobs() == []


def test_tasks_declare_the_shared_retry_limit() -> None:
    registered = _register()

    assert registered.ingest.max_retries == MAX_RETRIES
    assert registered.caption.max_retries == MAX_RETRIES


class _LoadCountingCaptioner(FakeCaptioner):
    loads = 0

    def load(self) -> None:
        self.loads += 1


class _RecordingBuilders:
    """Fake builders for `Workers` that record the settings each was called with."""

    def __init__(self) -> None:
        self.loader_calls: list[Settings] = []
        self.queue_calls: list[Settings] = []
        self.store_calls: list[Settings] = []
        self.dataset_calls: list[Settings] = []
        self.captioner = _LoadCountingCaptioner()

    def loader(self, settings: Settings, dataset: DatasetStore) -> SceneLoader:
        self.loader_calls.append(settings)
        return FakeSceneLoader([])

    def queue(self, settings: Settings) -> FakeJobQueue:
        self.queue_calls.append(settings)
        return FakeJobQueue()

    def store(self, settings: Settings) -> FakeJobStore:
        self.store_calls.append(settings)
        return FakeJobStore()

    def build_captioner(self, settings: Settings) -> Captioner:
        return self.captioner

    def dataset(self, settings: Settings) -> FakeDatasetStore:
        self.dataset_calls.append(settings)
        return FakeDatasetStore()


def _workers(builders: _RecordingBuilders, settings: Settings | None = None) -> tasks.Workers:
    return tasks.Workers(
        settings or make_settings(),
        build_loader=builders.loader,
        build_queue=builders.queue,
        build_store=builders.store,
        build_captioner=builders.build_captioner,
        build_dataset=builders.dataset,
    )


def test_ingest_worker_is_built_from_settings_and_cached() -> None:
    builders = _RecordingBuilders()
    settings = make_settings(nuscenes_dataroot="/data/nu", camera_channel="CAM_BACK")
    workers = _workers(builders, settings)

    first = workers.ingest_worker
    second = workers.ingest_worker

    assert first is second
    assert builders.loader_calls == [settings]
    assert builders.queue_calls == [settings]
    assert builders.store_calls == [settings]
    assert builders.dataset_calls == [settings]


def test_caption_worker_loads_the_model_once_and_is_cached() -> None:
    builders = _RecordingBuilders()
    workers = _workers(builders)

    first = workers.caption_worker
    second = workers.caption_worker

    assert first is second
    assert builders.captioner.loads == 1


def test_store_is_shared_between_workers() -> None:
    builders = _RecordingBuilders()
    workers = _workers(builders)

    _ = workers.ingest_worker
    _ = workers.caption_worker

    assert len(builders.store_calls) == 1


def test_workers_build_nothing_until_asked() -> None:
    builders = _RecordingBuilders()

    _workers(builders)

    assert builders.loader_calls == builders.queue_calls == builders.store_calls == builders.dataset_calls == []
    assert builders.captioner.loads == 0


def test_worker_logging_is_service_tagged() -> None:
    calls: list[tuple[LogFormat, str]] = []

    tasks.configure_worker_logging(make_settings(), setup=lambda fmt, service: calls.append((fmt, service)))

    assert calls == [(LogFormat.COLORED, "worker")]
