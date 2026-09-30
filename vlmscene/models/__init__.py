"""Domain models — pure Pydantic, no imports from api/, bl/, or cli/."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SceneKeyframe(BaseModel):
    """A single representative image picked to stand in for a whole scene."""

    scene_token: str
    scene_name: str
    camera_channel: str
    image_path: str


class SceneDescription(BaseModel):
    """A scene keyframe plus the natural-language description a VLM produced for it."""

    scene_token: str
    scene_name: str
    camera_channel: str
    image_path: str
    description: str
    model_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobState(StrEnum):
    """Lifecycle of a job, derived from scene counts rather than stored."""

    PENDING = "pending"  # ingest hasn't reported how many scenes there are yet
    RUNNING = "running"
    COMPLETED = "completed"


class Job(BaseModel):
    """A request to describe every scene of the dataset, with its current progress."""

    job_id: UUID
    state: JobState
    max_scenes: int | None
    expected_scenes: int | None
    completed_scenes: int
    created_at: datetime


class IngestTask(BaseModel):
    """Queue message: load the dataset and fan out one CaptionTask per scene."""

    job_id: UUID
    max_scenes: int | None = None


class CaptionTask(BaseModel):
    """Queue message: caption one scene's keyframe on behalf of a job."""

    job_id: UUID
    keyframe: SceneKeyframe
