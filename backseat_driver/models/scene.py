from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Camera(StrEnum):
    """The six cameras on a nuScenes vehicle, front-centre first then clockwise."""

    FRONT = "front"
    FRONT_RIGHT = "front_right"
    BACK_RIGHT = "back_right"
    BACK = "back"
    BACK_LEFT = "back_left"
    FRONT_LEFT = "front_left"

    @property
    def channel(self) -> str:
        """The name nuScenes gives this camera, e.g. `CAM_FRONT`."""
        return f"CAM_{self.name}"


class SceneKeyframe(BaseModel):
    """A single representative image picked to stand in for a whole scene."""

    scene_token: str
    scene_name: str
    camera_channel: str
    image_path: str
    reference_description: str | None = None  # nuScenes' own human-written scene label, used to score models


class SceneDescription(SceneKeyframe):
    """A scene keyframe plus the natural-language description a VLM produced for it."""

    description: str
    model_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
