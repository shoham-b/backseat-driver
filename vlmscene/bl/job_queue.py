"""Port for the distributed mode's work queue — how the API and the workers hand work to each other.

The broker-backed implementation (Celery over RabbitMQ) lives in `vlmscene.adapters`.
"""

from abc import ABC, abstractmethod

from vlmscene.models import CaptionTask, IngestTask


class JobQueue(ABC):
    """Anything that can hand ingest and caption tasks to the workers."""

    @abstractmethod
    def enqueue_ingest(self, task: IngestTask) -> None: ...

    @abstractmethod
    def enqueue_caption(self, task: CaptionTask) -> None: ...

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the broker is reachable."""
