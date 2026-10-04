"""Port for job state and results.
The SQL implementation (Postgres when distributed, SQLite for the monolith) lives next to it in `sql_job_store.py`.

A job's state is derived from how many scenes it expects versus how many
descriptions have been recorded (and whether an error was recorded), never stored. That removes the race a separate
"mark complete" step would have between concurrent caption workers.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from backseat_driver.models import DeadLetter, Job, JobDeadLetter, JobState, SceneDescription


class JobStore(ABC):
    """Anything that can track jobs and the scene descriptions produced for them."""

    @abstractmethod
    def create_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        """Record a new job. The database rejects a second job under the same `idempotency_key`."""

    @abstractmethod
    def find_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        """The job created under this key, or None."""

    @abstractmethod
    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        """Record how many descriptions the job will produce: one per scene and camera, which is what completion is
        counted against. Raises NotFoundError for an unknown job."""

    @abstractmethod
    def fail_job(self, job_id: UUID, error: str) -> None:
        """Mark the job failed. The first error is kept, so a later one can't hide the root cause.
        Raises NotFoundError for an unknown job."""

    @abstractmethod
    def record_dead_letter(self, job_id: UUID, dead_letter: DeadLetter) -> None:
        """Keep a task that ran out of retries, with its payload. Does not change the job's state: `fail_job` does.
        Raises NotFoundError for an unknown job."""

    @abstractmethod
    def list_dead_letters(self, job_id: UUID) -> list[DeadLetter]:
        """Oldest first. Raises NotFoundError for an unknown job."""

    @abstractmethod
    def list_recent_dead_letters(self, limit: int) -> list[JobDeadLetter]:
        """The newest `limit` dead letters across all jobs, newest first."""

    @abstractmethod
    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        """Store a description. Idempotent per (job, scene, camera): a redelivered message is a no-op."""

    @abstractmethod
    def get_job(self, job_id: UUID) -> Job:
        """Raises NotFoundError for an unknown job."""

    @abstractmethod
    def list_jobs(self) -> list[Job]:
        """Every job, newest first."""

    @abstractmethod
    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        """Raises NotFoundError for an unknown job."""

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the database is reachable."""


def derive_state(expected_scenes: int | None, completed_scenes: int, error: str | None) -> JobState:
    if error is not None:
        return JobState.FAILED
    if expected_scenes is None:
        return JobState.PENDING
    if completed_scenes >= expected_scenes:
        return JobState.COMPLETED
    return JobState.RUNNING
