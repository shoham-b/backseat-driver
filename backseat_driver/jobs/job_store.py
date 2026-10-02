"""Port for job state and results in the distributed mode.
The Postgres implementation lives next to it in `postgres_job_store.py`.

A job's state is derived from how many scenes it expects versus how many
descriptions have been recorded, never stored. That removes the race a separate
"mark complete" step would have between concurrent caption workers.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from backseat_driver.models import Job, JobState, SceneDescription


class JobStore(ABC):
    """Anything that can track jobs and the scene descriptions produced for them."""

    @abstractmethod
    def create_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None: ...

    @abstractmethod
    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        """Record how many scenes the job will produce. Raises NotFoundError for an unknown job."""

    @abstractmethod
    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        """Store a description. Idempotent per (job, scene): a redelivered message is a no-op."""

    @abstractmethod
    def get_job(self, job_id: UUID) -> Job:
        """Raises NotFoundError for an unknown job."""

    @abstractmethod
    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        """Raises NotFoundError for an unknown job."""

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the database is reachable."""


def derive_state(expected_scenes: int | None, completed_scenes: int) -> JobState:
    if expected_scenes is None:
        return JobState.PENDING
    if completed_scenes >= expected_scenes:
        return JobState.COMPLETED
    return JobState.RUNNING
