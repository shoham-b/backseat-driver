"""In-process implementation of the `JobQueue` port — the monolith's queue, so local dev needs no broker or workers.

Tasks run on one background thread inside the API process, using the same `IngestWorker` and
`CaptionWorker` handlers the Celery workers do. One thread, because that is what the solo-pool
caption worker is too: the model is not meant to run concurrently with itself.
"""

from collections.abc import Callable
from queue import Queue
from threading import Lock, Thread

from loguru import logger

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.transport.job_queue import JobQueue


class InProcessJobQueue(JobQueue):
    """Runs tasks on a daemon thread, started on the first task. Constructing it never starts anything."""

    def __init__(self) -> None:
        self._tasks: Queue[tuple[Callable[[], None], IngestTask | CaptionTask]] = Queue()
        self._thread: Thread | None = None
        self._start_lock = Lock()
        self._on_ingest: Callable[[IngestTask], None] | None = None
        self._on_caption: Callable[[CaptionTask], None] | None = None
        self._on_failure: Callable[[IngestTask | CaptionTask, Exception], None] | None = None

    def register(
        self,
        on_ingest: Callable[[IngestTask], None],
        on_caption: Callable[[CaptionTask], None],
        on_failure: Callable[[IngestTask | CaptionTask, Exception], None],
    ) -> None:
        """Set the handlers. Separate from `__init__` because the ingest handler itself needs this queue.

        `on_failure` is told about a task whose handler raised: there are no retries here, so that is final."""
        self._on_ingest = on_ingest
        self._on_caption = on_caption
        self._on_failure = on_failure

    def enqueue_ingest(self, task: IngestTask) -> None:
        if self._on_ingest is None:
            raise RuntimeError("InProcessJobQueue.register() must be called before enqueueing")
        self._submit(self._on_ingest, task)

    def enqueue_caption(self, task: CaptionTask) -> None:
        if self._on_caption is None:
            raise RuntimeError("InProcessJobQueue.register() must be called before enqueueing")
        self._submit(self._on_caption, task)

    def healthcheck(self) -> bool:
        return True

    def _submit[T: IngestTask | CaptionTask](self, handler: Callable[[T], None], task: T) -> None:
        self._ensure_thread()
        self._tasks.put((lambda: handler(task), task))

    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is None:
                self._thread = Thread(target=self._run, name="in-process-worker", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            run, task = self._tasks.get()
            try:
                run()
            except Exception as exc:
                # Like the Celery workers once retries are exhausted: record the failure and drop the task, so one bad
                # task can't stop the rest.
                logger.exception("in-process task failed")
                self._report_failure(task, exc)

    def _report_failure(self, task: IngestTask | CaptionTask, error: Exception) -> None:
        assert self._on_failure is not None  # _submit only runs after register()
        try:
            self._on_failure(task, error)
        except Exception:
            # Same constraint: a store that is down must not kill the thread that every later task needs.
            logger.exception("could not record the failure of job {}", task.job_id)
