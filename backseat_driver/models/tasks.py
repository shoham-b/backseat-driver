from backseat_driver.models.job import JobReference
from backseat_driver.models.scene import SceneKeyframe


class IngestTask(JobReference):
    """Queue message: load the dataset and fan out one CaptionTask per keyframe (scene and camera)."""

    max_scenes: int | None = None  # counts scenes, not keyframes


class CaptionTask(JobReference):
    """Queue message: caption one scene's keyframe on behalf of a job."""

    keyframe: SceneKeyframe
    image_uri: str  # where the image bytes are; the keyframe's `image_path` is only the key they are stored under
