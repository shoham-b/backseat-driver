import json
from pathlib import Path

from backseat_driver.bl.writer import write_json
from backseat_driver.models import SceneDescription


def _description(n: int) -> SceneDescription:
    return SceneDescription(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n}",
        camera_channel="CAM_FRONT",
        image_path=f"/data/scene-{n}.jpg",
        description=f"description {n}",
        model_name="fake-model",
    )


def test_write_json_creates_parent_directories(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "results.json"

    write_json([_description(1)], str(output_path))

    assert output_path.exists()


def test_write_json_writes_one_object_per_scene(tmp_path: Path) -> None:
    output_path = tmp_path / "results.json"
    descriptions = [_description(1), _description(2)]

    write_json(descriptions, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert payload[0]["scene_name"] == "scene-1"
    assert payload[0]["description"] == "description 1"
    assert payload[1]["scene_name"] == "scene-2"


def test_write_json_on_empty_list_writes_empty_array(tmp_path: Path) -> None:
    output_path = tmp_path / "results.json"

    write_json([], str(output_path))

    assert json.loads(output_path.read_text(encoding="utf-8")) == []
