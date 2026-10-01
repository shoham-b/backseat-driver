"""Port for reading scenes from a dataset. Concrete loaders live in `vlmscene.adapters`."""

from abc import ABC, abstractmethod

from vlmscene.models import SceneKeyframe


class SceneLoader(ABC):
    """Anything that can produce one representative keyframe per scene."""

    @abstractmethod
    def load_keyframes(self) -> list[SceneKeyframe]: ...
