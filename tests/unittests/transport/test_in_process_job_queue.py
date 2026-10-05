import threading
from uuid import uuid4

import pytest

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.in_process_job_queue import InProcessJobQueue
from tests.fakes import make_image_uri, make_keyframe


def _ingest_task() -> IngestTask:
    return IngestTask(job_id=uuid4(), transaction_id="tx")


def _caption_task() -> CaptionTask:
    return CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))


def test_tasks_run_in_order_on_one_background_thread() -> None:
    queue = InProcessJobQueue()
    seen: list[tuple[str, str]] = []
    done = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        seen.append(("ingest", threading.current_thread().name))

    def on_caption(task: CaptionTask) -> None:
        seen.append(("caption", threading.current_thread().name))
        done.set()

    queue.register(on_ingest, on_caption, on_failure=lambda task, error: None)

    queue.enqueue_ingest(_ingest_task())
    queue.enqueue_caption(_caption_task())

    assert done.wait(timeout=5)
    assert seen == [("ingest", "in-process-worker"), ("caption", "in-process-worker")]


def test_a_failing_task_does_not_stop_later_tasks() -> None:
    queue = InProcessJobQueue()
    later_task_ran = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    queue.register(on_ingest, lambda task: later_task_ran.set(), on_failure=lambda task, error: None)

    queue.enqueue_ingest(_ingest_task())
    queue.enqueue_caption(_caption_task())

    assert later_task_ran.wait(timeout=5)


def test_a_failing_task_is_reported_with_its_error() -> None:
    queue = InProcessJobQueue()
    reported: list[tuple[IngestTask | CaptionTask, Exception]] = []
    reported_event = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    def on_failure(task: IngestTask | CaptionTask, error: Exception) -> None:
        reported.append((task, error))
        reported_event.set()

    queue.register(on_ingest, lambda task: None, on_failure=on_failure)
    task = _ingest_task()

    queue.enqueue_ingest(task)

    assert reported_event.wait(timeout=5)
    assert [(t, str(e)) for t, e in reported] == [(task, "boom")]


def test_a_failure_that_cannot_be_recorded_does_not_stop_later_tasks() -> None:
    queue = InProcessJobQueue()
    later_task_ran = threading.Event()

    def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    def on_failure(task: IngestTask | CaptionTask, error: Exception) -> None:
        raise ConnectionError("store down")

    queue.register(on_ingest, lambda task: later_task_ran.set(), on_failure=on_failure)

    queue.enqueue_ingest(_ingest_task())
    queue.enqueue_caption(_caption_task())

    assert later_task_ran.wait(timeout=5)


@pytest.mark.parametrize("enqueue", ["enqueue_ingest", "enqueue_caption"])
def test_enqueueing_before_register_fails_fast(enqueue: str) -> None:
    queue = InProcessJobQueue()
    task = _ingest_task() if enqueue == "enqueue_ingest" else _caption_task()

    with pytest.raises(RuntimeError, match="register"):
        getattr(queue, enqueue)(task)


def test_the_queue_is_healthy_and_starts_no_thread_until_used() -> None:
    threads_before = threading.active_count()

    queue = InProcessJobQueue()

    assert queue.healthcheck() is True
    assert threading.active_count() == threads_before
