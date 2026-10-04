"""Port for how the workers reach keyframe images: by URI, with no filesystem shared between them.

Image keys are dataset-relative paths (`samples/CAM_FRONT/<name>.jpg`), the same string `SceneKeyframe.image_path`
holds everywhere. Ingest turns a key into a URI for the queue message and the caption worker borrows a
local copy of the object behind it.
"""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path


class ImageStore(ABC):
    @abstractmethod
    def uri_for(self, key: str) -> str:
        """The URI a caption worker fetches the image at `key` by."""

    @abstractmethod
    def local_copy(self, uri: str) -> AbstractContextManager[Path]:
        """A local file holding the image at `uri`, valid inside the `with` block and cleaned up after it."""
