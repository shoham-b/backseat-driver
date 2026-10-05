"""In-process implementation of the `JobQueue` port — the monolith's queue, so local dev needs no broker or workers.

Tasks run one at a time on a task of the running event loop (the API's), using the same `IngestWorker` and
`CaptionWorker` handlers the Celery workers do. One consumer, because that is what the solo-pool caption worker is
too: the model is not meant to run concurrently with itself. It shares the API's loop, so it can share the API's
database connections.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from loguru import logger

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.job_queue import JobQueue


class InProcessJobQueue(JobQueue):
    """Runs tasks on a consumer task started with the first one. Constructing it never starts anything."""

    def __init__(self) -> None:
        self._tasks: asyncio.Queue[tuple[Callable[[], Awaitable[None]], IngestTask | CaptionTask]] | None = None
        self._consumer: asyncio.Task[None] | None = None
        self._on_ingest: Callable[[IngestTask], Awaitable[None]] | None = None
        self._on_caption: Callable[[CaptionTask], Awaitable[None]] | None = None
        self._on_failure: Callable[[IngestTask | CaptionTask, Exception], Awaitable[None]] | None = None

    def register(
        self,
        on_ingest: Callable[[IngestTask], Awaitable[None]],
        on_caption: Callable[[CaptionTask], Awaitable[None]],
        on_failure: Callable[[IngestTask | CaptionTask, Exception], Awaitable[None]],
    ) -> None:
        """Set the handlers. Separate from `__init__` because the ingest handler itself needs this queue.

        `on_failure` is told about a task whose handler raised: there are no retries here, so that is final."""
        self._on_ingest = on_ingest
        self._on_caption = on_caption
        self._on_failure = on_failure

    async def enqueue_ingest(self, task: IngestTask) -> None:
        if self._on_ingest is None:
            raise RuntimeError("InProcessJobQueue.register() must be called before enqueueing")
        self._submit(self._on_ingest, task)

    async def enqueue_caption(self, task: CaptionTask) -> None:
        if self._on_caption is None:
            raise RuntimeError("InProcessJobQueue.register() must be called before enqueueing")
        self._submit(self._on_caption, task)

    async def healthcheck(self) -> bool:
        return True

    async def aclose(self) -> None:
        """Stop the consumer; tasks still waiting are dropped."""
        if self._consumer is not None:
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer
            self._consumer = None

    def _submit[T: IngestTask | CaptionTask](self, handler: Callable[[T], Awaitable[None]], task: T) -> None:
        if self._tasks is None or self._consumer is None:
            self._tasks = asyncio.Queue()
            self._consumer = asyncio.create_task(self._run(self._tasks), name="in-process-worker")
        self._tasks.put_nowait((lambda: handler(task), task))

    async def _run(self, tasks: asyncio.Queue[tuple[Callable[[], Awaitable[None]], IngestTask | CaptionTask]]) -> None:
        while True:
            run, task = await tasks.get()
            try:
                await run()
            except Exception as exc:
                # Like the Celery workers once retries are exhausted: record the failure and drop the task, so one bad
                # task can't stop the rest.
                logger.exception("in-process task failed")
                await self._report_failure(task, exc)

    async def _report_failure(self, task: IngestTask | CaptionTask, error: Exception) -> None:
        assert self._on_failure is not None  # _submit only runs after register()
        try:
            await self._on_failure(task, error)
        except Exception:
            # Same constraint: a store that is down must not kill the consumer that every later task needs.
            logger.exception("could not record the failure of job {}", task.job_id)
