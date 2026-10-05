import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.in_process_job_queue import InProcessJobQueue
from tests.fakes import make_image_uri, make_keyframe


def _ingest_task() -> IngestTask:
    return IngestTask(job_id=uuid4(), transaction_id="tx")


def _caption_task() -> CaptionTask:
    return CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))


async def _no_failure_handler(task: IngestTask | CaptionTask, error: Exception) -> None:
    return None


@pytest.fixture
async def queue() -> AsyncIterator[InProcessJobQueue]:
    queue = InProcessJobQueue()
    yield queue
    await queue.close()


async def test_tasks_run_in_order_on_one_consumer_task(queue: InProcessJobQueue) -> None:
    seen: list[tuple[str, str]] = []
    done = asyncio.Event()

    async def on_ingest(task: IngestTask) -> None:
        seen.append(("ingest", _current_task_name()))

    async def on_caption(task: CaptionTask) -> None:
        seen.append(("caption", _current_task_name()))
        done.set()

    queue.register(on_ingest, on_caption, on_failure=_no_failure_handler)

    await queue.enqueue_ingest(_ingest_task())
    await queue.enqueue_caption(_caption_task())

    await asyncio.wait_for(done.wait(), timeout=5)
    assert seen == [("ingest", "in-process-worker"), ("caption", "in-process-worker")]


def _current_task_name() -> str:
    task = asyncio.current_task()
    assert task is not None
    return task.get_name()


async def test_a_failing_task_does_not_stop_later_tasks(queue: InProcessJobQueue) -> None:
    later_task_ran = asyncio.Event()

    async def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    async def on_caption(task: CaptionTask) -> None:
        later_task_ran.set()

    queue.register(on_ingest, on_caption, on_failure=_no_failure_handler)

    await queue.enqueue_ingest(_ingest_task())
    await queue.enqueue_caption(_caption_task())

    await asyncio.wait_for(later_task_ran.wait(), timeout=5)


async def test_a_failing_task_is_reported_with_its_error(queue: InProcessJobQueue) -> None:
    reported: list[tuple[IngestTask | CaptionTask, Exception]] = []
    reported_event = asyncio.Event()

    async def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    async def on_caption(task: CaptionTask) -> None:
        return None

    async def on_failure(task: IngestTask | CaptionTask, error: Exception) -> None:
        reported.append((task, error))
        reported_event.set()

    queue.register(on_ingest, on_caption, on_failure=on_failure)
    task = _ingest_task()

    await queue.enqueue_ingest(task)

    await asyncio.wait_for(reported_event.wait(), timeout=5)
    assert [(t, str(e)) for t, e in reported] == [(task, "boom")]


async def test_a_failure_that_cannot_be_recorded_does_not_stop_later_tasks(queue: InProcessJobQueue) -> None:
    later_task_ran = asyncio.Event()

    async def on_ingest(task: IngestTask) -> None:
        raise RuntimeError("boom")

    async def on_caption(task: CaptionTask) -> None:
        later_task_ran.set()

    async def on_failure(task: IngestTask | CaptionTask, error: Exception) -> None:
        raise ConnectionError("store down")

    queue.register(on_ingest, on_caption, on_failure=on_failure)

    await queue.enqueue_ingest(_ingest_task())
    await queue.enqueue_caption(_caption_task())

    await asyncio.wait_for(later_task_ran.wait(), timeout=5)


@pytest.mark.parametrize("enqueue", ["enqueue_ingest", "enqueue_caption"])
async def test_enqueueing_before_register_fails_fast(queue: InProcessJobQueue, enqueue: str) -> None:
    task = _ingest_task() if enqueue == "enqueue_ingest" else _caption_task()

    with pytest.raises(RuntimeError, match="register"):
        await getattr(queue, enqueue)(task)


async def test_the_queue_is_healthy_and_starts_no_consumer_until_used() -> None:
    tasks_before = len(asyncio.all_tasks())

    queue = InProcessJobQueue()

    assert await queue.healthcheck() is True
    assert len(asyncio.all_tasks()) == tasks_before


async def test_closing_the_queue_stops_its_consumer() -> None:
    queue = InProcessJobQueue()
    ran = asyncio.Event()

    async def on_caption(task: CaptionTask) -> None:
        ran.set()

    async def on_ingest(task: IngestTask) -> None:
        return None

    queue.register(on_ingest, on_caption, on_failure=_no_failure_handler)
    await queue.enqueue_caption(_caption_task())
    await asyncio.wait_for(ran.wait(), timeout=5)
    tasks_while_running = len(asyncio.all_tasks())

    await queue.close()

    assert len(asyncio.all_tasks()) == tasks_while_running - 1
