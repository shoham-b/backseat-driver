"""Writes pipeline results out as JSON."""

import json
from pathlib import Path

from vlmscene.models import SceneDescription


def write_json(descriptions: list[SceneDescription], path: str) -> None:
    """Write descriptions to `path` as a JSON array, one object per scene."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = [d.model_dump(mode="json") for d in descriptions]
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
