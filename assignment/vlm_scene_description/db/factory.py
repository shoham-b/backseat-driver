from vlm_scene_description.config import Settings
from vlm_scene_description.db.base import Repository
from vlm_scene_description.db.memory import MemoryRepository


def get_repository(settings: Settings) -> Repository:
    """Select and instantiate the correct Repository implementation from settings."""

    return MemoryRepository()

