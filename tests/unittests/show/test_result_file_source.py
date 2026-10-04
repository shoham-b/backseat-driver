import json
from pathlib import Path

import pytest

from backseat_driver.process.http_client import HttpResponse
from backseat_driver.read.images.local_image_store import LocalImageStore
from backseat_driver.show.result_file_source import ResultFileSource


def _item(text: str) -> dict[str, object]:
    return {
        "scene_token": "t",
        "scene_name": "scene-0001",
        "camera_channel": "CAM_FRONT",
        "image_path": "a.jpg",
        "description": text,
        "model_name": "m",
    }


def test_the_descriptions_of_every_file_come_back_in_order(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text(json.dumps([_item("one")]))
    (tmp_path / "b.json").write_text(json.dumps([_item("two")]))

    descriptions = ResultFileSource(
        [tmp_path / "a.json", tmp_path / "b.json"], LocalImageStore(str(tmp_path))
    ).descriptions()

    assert [d.description for d in descriptions] == ["one", "two"]


def test_a_directory_is_read_for_its_json_files_only(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text(json.dumps([_item("one")]))
    (tmp_path / "notes.txt").write_text("not a result")

    source = ResultFileSource.in_directory(tmp_path, LocalImageStore(str(tmp_path)))

    assert [d.description for d in source.descriptions()] == ["one"]


def test_an_image_is_the_dataroot_file_with_its_guessed_type(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"jpeg")

    response = ResultFileSource([], LocalImageStore(str(tmp_path))).image("scene.jpg")

    assert response == HttpResponse(b"jpeg", "image/jpeg")


def test_a_missing_image_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ResultFileSource([], LocalImageStore(str(tmp_path))).image("gone.jpg")


def test_local_images_are_never_linked(tmp_path: Path) -> None:
    assert ResultFileSource([], LocalImageStore(str(tmp_path))).image_link("a.jpg") is None
