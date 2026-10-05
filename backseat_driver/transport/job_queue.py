"""Port for the distributed mode's work queue — how the API and the workers hand work to each other.

The broker-backed implementation (Celery over RabbitMQ) lives next to it in `celery_job_queue.py`.
"""

from abc import ABC, abstractmethod

from backseat_driver.models import CaptionTask, IngestTask


class JobQueue(ABC):
    """Anything that can hand ingest and caption tasks to the workers."""

    @abstractmethod
    async def enqueue_ingest(self, task: IngestTask) -> None: ...

    @abstractmethod
    async def enqueue_caption(self, task: CaptionTask) -> None: ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        """True if the broker is reachable."""

    async def close(self) -> None:  # noqa: B027  # optional: most queues run nothing in the background
        """Stop what the queue runs in the background. The default runs nothing."""
