from typing import Any
from uuid import uuid4

import pytest
from kombu.exceptions import OperationalError as KombuOperationalError

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.celery_app import CAPTION_TASK, INGEST_TASK
from backseat_driver.transport.celery_job_queue import CeleryJobQueue
from tests.fakes import FakeCeleryApp, FakeCeleryConnection, make_image_uri, make_keyframe

BROKER = "amqp://guest:guest@broker:5672/"


def _queue(app: FakeCeleryApp) -> CeleryJobQueue:
    return CeleryJobQueue(BROKER, make_app=lambda broker_url: app)


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
