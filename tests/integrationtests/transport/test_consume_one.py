"""`worker ingest --once` over a real (in-memory) Celery broker: exactly one queued task is run and acked."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from celery import Celery
from kombu.transport.memory import Channel

from backseat_driver import tasks
from backseat_driver.models import IngestTask
from backseat_driver.transport.celery_job_queue import INGEST_QUEUE, INGEST_TASK, make_celery_app
from backseat_driver.transport.consume_one import consume_one
from backseat_driver.transport.workers import CaptionWorker, IngestWorker
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe


@pytest.fixture(autouse=True)
def _empty_broker() -> Iterator[None]:
    """The in-memory broker is process-wide, so a message left by one test would reach the next."""
    Channel.queues.clear()
    yield
    Channel.queues.clear()


class _Failing(IngestWorker):
    def __init__(self) -> None:
        super().__init__(FakeSceneLoader([]), FakeJobQueue(), FakeJobStore(), FakeImageStore())
        self.calls = 0

    def handle(self, task: IngestTask) -> None:
        self.calls += 1
        raise ConnectionError("object store down")


def _app_with(ingest_worker: IngestWorker) -> Celery:
    app = make_celery_app("memory://")
    tasks.register_tasks(
        app, lambda: ingest_worker, lambda: CaptionWorker(FakeCaptioner(), FakeJobStore(), FakeImageStore())
    )
    return app


def _send(app: Celery, job_id: UUID | None = None) -> None:
    payload = IngestTask(job_id=job_id or uuid4(), transaction_id="tx").model_dump(mode="json")
    app.send_task(INGEST_TASK, args=[payload])


def _waiting(app: Celery) -> int:
    with app.connection_for_read() as connection:
        return connection.default_channel.queue_declare(INGEST_QUEUE, passive=True).message_count


def test_one_task_is_handled_and_the_rest_stay_queued() -> None:
    job_id, store, queue = uuid4(), FakeJobStore(), FakeJobQueue()
    store.create_job(job_id, None, "tx")
    app = _app_with(IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore()))
    _send(app, job_id)
    _send(app)

    handled = consume_one(app, INGEST_QUEUE)

    assert handled is True
    assert store.get_job(job_id).expected_scenes == 2
    assert len(queue.caption_tasks) == 2
    assert _waiting(app) == 1


def test_an_empty_queue_is_not_an_error() -> None:
    app = _app_with(_Failing())

    assert consume_one(app, INGEST_QUEUE) is False


def test_a_task_that_keeps_failing_is_retried_then_dropped_and_the_job_fails() -> None:
    worker = _Failing()
    app = _app_with(worker)
    _send(app)

    with pytest.raises(RuntimeError, match="dropped"):
        consume_one(app, INGEST_QUEUE)

    assert worker.calls == tasks.MAX_RETRIES + 1
    assert _waiting(app) == 0


def test_a_malformed_task_is_dropped_without_running_the_worker() -> None:
    worker = _Failing()
    app = _app_with(worker)
    app.send_task(INGEST_TASK, args=[{"job_id": "not-a-uuid"}])

    with pytest.raises(RuntimeError, match="dropped"):
        consume_one(app, INGEST_QUEUE)

    assert worker.calls == 0
    assert _waiting(app) == 0
