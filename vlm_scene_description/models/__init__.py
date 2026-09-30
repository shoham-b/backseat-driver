"""Domain models — pure Pydantic, no imports from api/, bl/, or cli/."""

from datetime import UTC, datetime

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
