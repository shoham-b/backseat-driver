"""Writes pipeline results out as JSON."""

from vlm_scene_description.models import SceneDescription


def write_json(descriptions: list[SceneDescription], path: str) -> None:
    """Write descriptions to `path` as a JSON array, one object per scene."""
    raise NotImplementedError
