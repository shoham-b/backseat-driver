from typing import Any
from uuid import uuid4

import pytest
from kombu.exceptions import OperationalError as KombuOperationalError

from backseat_driver.jobs.celery_job_queue import (
    CAPTION_QUEUE,
    CAPTION_TASK,
    INGEST_QUEUE,
    INGEST_TASK,
    MAX_RETRIES,
    CeleryJobQueue,
    make_celery_app,
)
from backseat_driver.models import CaptionTask, IngestTask
from tests.fakes import FakeCeleryApp, FakeCeleryConnection, make_image_uri, make_keyframe

BROKER = "amqp://guest:guest@broker:5672/"


def _queue(app: FakeCeleryApp) -> CeleryJobQueue:
    return CeleryJobQueue(BROKER, make_app=lambda broker_url: app)


def test_celery_app_is_configured_for_durable_at_least_once_delivery() -> None:
    conf = make_celery_app(BROKER).conf

    assert conf.broker_url == BROKER
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_ignore_result is True
    assert conf.broker_transport_options == {"confirm_publish": True}
    assert conf.worker_enable_remote_control is False


def test_celery_app_declares_both_queues_as_quorum_queues() -> None:
    queues = {q.name: q for q in make_celery_app(BROKER).conf.task_queues}

    assert set(queues) == {INGEST_QUEUE, CAPTION_QUEUE}
    assert all(q.queue_arguments == {"x-queue-type": "quorum"} for q in queues.values())
    assert all(q.routing_key == q.name for q in queues.values())


def test_tasks_are_routed_to_their_own_queues() -> None:
    routes = make_celery_app(BROKER).conf.task_routes

    assert routes == {INGEST_TASK: {"queue": INGEST_QUEUE}, CAPTION_TASK: {"queue": CAPTION_QUEUE}}


def test_max_retries_is_bounded() -> None:
    assert MAX_RETRIES > 0


def test_constructing_the_queue_never_builds_a_celery_app() -> None:
    built: list[str] = []

    CeleryJobQueue(BROKER, make_app=lambda broker_url: built.append(broker_url))

    assert built == []


def test_enqueue_ingest_publishes_a_json_payload_by_task_name() -> None:
    app = FakeCeleryApp()
    task = IngestTask(job_id=uuid4(), transaction_id="tx-1", max_scenes=2)

    _queue(app).enqueue_ingest(task)

    assert app.sent == [(INGEST_TASK, [task.model_dump(mode="json")])]
    [(_, [payload])] = app.sent
    assert payload["job_id"] == str(task.job_id)  # JSON-safe, not a UUID object


def test_enqueue_caption_publishes_a_json_payload_by_task_name() -> None:
    app = FakeCeleryApp()
    task = CaptionTask(job_id=uuid4(), transaction_id="tx-1", keyframe=make_keyframe(1), image_uri=make_image_uri(1))

    _queue(app).enqueue_caption(task)

    assert app.sent == [(CAPTION_TASK, [task.model_dump(mode="json")])]


def test_app_is_built_once_and_reused() -> None:
    built: list[str] = []
    app = FakeCeleryApp()

    def make_app(broker_url: str) -> Any:
        built.append(broker_url)
        return app

    queue = CeleryJobQueue(BROKER, make_app=make_app)

    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="a"))
    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="b"))
    queue.healthcheck()

    assert built == [BROKER]


def test_publish_failures_are_not_swallowed() -> None:
    app = FakeCeleryApp(publish_error=KombuOperationalError("broker down"))

    with pytest.raises(KombuOperationalError):
        _queue(app).enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="tx"))


def test_healthcheck_is_true_when_the_broker_accepts_a_connection() -> None:
    app = FakeCeleryApp()

    healthy = _queue(app).healthcheck()

    assert healthy is True
    assert app.connection.ensure_calls == [1]


@pytest.mark.parametrize(
    "error", [KombuOperationalError("refused"), ConnectionRefusedError("refused"), OSError("down")]
)
def test_healthcheck_is_false_when_the_broker_is_unreachable(error: Exception) -> None:
    app = FakeCeleryApp(connection=FakeCeleryConnection(error=error))

    assert _queue(app).healthcheck() is False


def test_healthcheck_propagates_unexpected_errors() -> None:
    app = FakeCeleryApp(connection=FakeCeleryConnection(error=RuntimeError("bug")))

    with pytest.raises(RuntimeError, match="bug"):
        _queue(app).healthcheck()
