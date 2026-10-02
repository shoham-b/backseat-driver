from unittest import mock
from uuid import uuid4

import pytest
from kombu.exceptions import OperationalError as KombuOperationalError

from backseat_driver.jobs import celery_job_queue
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
from tests.fakes import make_keyframe

BROKER = "amqp://guest:guest@broker:5672/"


@pytest.fixture
def fake_app(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    app = mock.MagicMock()
    monkeypatch.setattr(celery_job_queue, "make_celery_app", lambda broker_url: app)
    return app


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


def test_constructing_the_queue_never_builds_a_celery_app(monkeypatch: pytest.MonkeyPatch) -> None:
    build = mock.MagicMock()
    monkeypatch.setattr(celery_job_queue, "make_celery_app", build)

    CeleryJobQueue(BROKER)

    build.assert_not_called()


def test_enqueue_ingest_publishes_a_json_payload_by_task_name(fake_app: mock.MagicMock) -> None:
    task = IngestTask(job_id=uuid4(), transaction_id="tx-1", max_scenes=2)

    CeleryJobQueue(BROKER).enqueue_ingest(task)

    fake_app.send_task.assert_called_once_with(INGEST_TASK, args=[task.model_dump(mode="json")])
    [payload] = fake_app.send_task.call_args.kwargs["args"]
    assert payload["job_id"] == str(task.job_id)  # JSON-safe, not a UUID object


def test_enqueue_caption_publishes_a_json_payload_by_task_name(fake_app: mock.MagicMock) -> None:
    task = CaptionTask(job_id=uuid4(), transaction_id="tx-1", keyframe=make_keyframe(1))

    CeleryJobQueue(BROKER).enqueue_caption(task)

    fake_app.send_task.assert_called_once_with(CAPTION_TASK, args=[task.model_dump(mode="json")])


def test_app_is_built_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    build = mock.MagicMock()
    monkeypatch.setattr(celery_job_queue, "make_celery_app", build)
    queue = CeleryJobQueue(BROKER)

    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="a"))
    queue.enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="b"))
    queue.healthcheck()

    build.assert_called_once_with(BROKER)


def test_publish_failures_are_not_swallowed(fake_app: mock.MagicMock) -> None:
    fake_app.send_task.side_effect = KombuOperationalError("broker down")

    with pytest.raises(KombuOperationalError):
        CeleryJobQueue(BROKER).enqueue_ingest(IngestTask(job_id=uuid4(), transaction_id="tx"))


def test_healthcheck_is_true_when_the_broker_accepts_a_connection(fake_app: mock.MagicMock) -> None:
    healthy = CeleryJobQueue(BROKER).healthcheck()

    connection = fake_app.connection_for_write.return_value.__enter__.return_value
    assert healthy is True
    connection.ensure_connection.assert_called_once_with(max_retries=1)


@pytest.mark.parametrize(
    "error", [KombuOperationalError("refused"), ConnectionRefusedError("refused"), OSError("down")]
)
def test_healthcheck_is_false_when_the_broker_is_unreachable(fake_app: mock.MagicMock, error: Exception) -> None:
    fake_app.connection_for_write.return_value.__enter__.return_value.ensure_connection.side_effect = error

    assert CeleryJobQueue(BROKER).healthcheck() is False


def test_healthcheck_propagates_unexpected_errors(fake_app: mock.MagicMock) -> None:
    fake_app.connection_for_write.side_effect = RuntimeError("bug")

    with pytest.raises(RuntimeError, match="bug"):
        CeleryJobQueue(BROKER).healthcheck()
