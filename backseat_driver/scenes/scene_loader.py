"""Port for reading scenes from a dataset. The nuScenes loader lives next to it."""

from abc import ABC, abstractmethod

from backseat_driver.models import SceneKeyframe


class SceneLoader(ABC):
    """Anything that can produce one representative keyframe per scene."""

    @abstractmethod
    def load_keyframes(self) -> list[SceneKeyframe]: ...
