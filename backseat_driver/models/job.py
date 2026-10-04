from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class JobReference(BaseModel):
    """What ties a job's row, its queue messages and every worker log line together."""

    job_id: UUID
    transaction_id: str  # correlates the API request, the job row, every queue message and worker log line


class JobState(StrEnum):
    """Lifecycle of a job, derived from scene counts and the recorded error rather than stored."""

    PENDING = "pending"  # ingest hasn't reported how many scenes there are yet
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"  # a task ran out of retries (or the job could not be enqueued); `Job.error` says why


class Job(JobReference):
    """A request to describe every scene of the dataset, with its current progress."""

    state: JobState
    max_scenes: int | None
    expected_scenes: int | None
    completed_scenes: int
    created_at: datetime
    error: str | None = None
