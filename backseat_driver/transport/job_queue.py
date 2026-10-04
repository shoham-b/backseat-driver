"""Port for the work queue — how the API and the workers hand work to each other.

The monolith runs it on a thread (`in_process_job_queue.py`); the distributed mode runs it over a
broker (Celery over RabbitMQ, `celery_job_queue.py`).
"""

from abc import ABC, abstractmethod

from backseat_driver.models import CaptionTask, IngestTask


class JobQueue(ABC):
    """Anything that can hand ingest and caption tasks to the workers."""

    @abstractmethod
    def enqueue_ingest(self, task: IngestTask) -> None: ...

    @abstractmethod
    def enqueue_caption(self, task: CaptionTask) -> None: ...

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the broker is reachable."""
