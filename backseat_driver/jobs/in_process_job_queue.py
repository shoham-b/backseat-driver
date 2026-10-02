"""In-process implementation of the `JobQueue` port — the monolith's queue, so local dev needs no broker or workers.

Tasks run on one background thread inside the API process, using the same `IngestWorker` and
`CaptionWorker` handlers the Celery workers do. One thread, because that is what the solo-pool
caption worker is too: the model is not meant to run concurrently with itself.
"""

from collections.abc import Callable
from queue import Queue
from threading import Lock, Thread

from loguru import logger

from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.models import CaptionTask, IngestTask


class InProcessJobQueue(JobQueue):
    """Runs tasks on a daemon thread, started on the first task. Constructing it never starts anything."""

    def __init__(self) -> None:
        self._tasks: Queue[Callable[[], None]] = Queue()
        self._thread: Thread | None = None
        self._start_lock = Lock()
        self._on_ingest: Callable[[IngestTask], None] | None = None
        self._on_caption: Callable[[CaptionTask], None] | None = None

    def register(self, on_ingest: Callable[[IngestTask], None], on_caption: Callable[[CaptionTask], None]) -> None:
        """Set the handlers. Separate from `__init__` because the ingest handler itself needs this queue."""
        self._on_ingest = on_ingest
        self._on_caption = on_caption

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
        self._tasks.put(lambda: handler(task))

    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is None:
                self._thread = Thread(target=self._run, name="in-process-worker", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            run = self._tasks.get()
            try:
                run()
            except Exception:
                # Like the Celery workers once retries are exhausted: log and drop, so one bad task can't stop the rest.
                logger.exception("in-process task failed")
