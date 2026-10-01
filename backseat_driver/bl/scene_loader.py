"""Port for reading scenes from a dataset. Concrete loaders live in `backseat_driver.adapters`."""

from abc import ABC, abstractmethod

from backseat_driver.models import SceneKeyframe


class SceneLoader(ABC):
    """Anything that can produce one representative keyframe per scene."""

    @abstractmethod
    def load_keyframes(self) -> list[SceneKeyframe]: ...
