import shutil
from pathlib import Path

import pytest

from backseat_driver.read.dataset.nuscenes_scene_loader import NuScenesSceneLoader, open_nuscenes
from backseat_driver.read.dataset.nuscenes_tables import NuScenesTables
from tests.nuscenes_dataset import VERSION, build_nuscenes_dataset, middle_image


def test_scenes_and_records_are_read_from_the_json_tables(tmp_path: Path) -> None:
    dataroot = build_nuscenes_dataset(tmp_path)

    tables = NuScenesTables(VERSION, str(dataroot))

    assert [scene["name"] for scene in tables.scene] == ["scene-0000", "scene-0001"]
    first_sample = tables.get("sample", tables.scene[0]["first_sample_token"])
    assert first_sample["next"]


def test_a_sample_maps_each_camera_channel_to_its_key_frame_sample_data(tmp_path: Path) -> None:
    tables = NuScenesTables(VERSION, str(build_nuscenes_dataset(tmp_path)))
    sample = tables.get("sample", tables.scene[0]["first_sample_token"])

    sample_data = tables.get("sample_data", sample["data"]["CAM_FRONT"])

    assert list(sample["data"]) == ["CAM_FRONT"]
    assert sample_data["filename"] == "samples/CAM_FRONT/scene0_frame0.jpg"


def test_an_unknown_token_raises_instead_of_returning_nothing(tmp_path: Path) -> None:
    tables = NuScenesTables(VERSION, str(build_nuscenes_dataset(tmp_path)))

    with pytest.raises(KeyError):
        tables.get("sample", "no-such-token")


def test_a_missing_table_file_fails_when_opening_or_reading(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        NuScenesTables(VERSION, str(tmp_path))


async def test_keyframes_are_found_without_the_maps_or_any_image(tmp_path: Path) -> None:
    dataroot = build_nuscenes_dataset(tmp_path)
    shutil.rmtree(dataroot / "maps")
    shutil.rmtree(dataroot / "samples")
    loader = NuScenesSceneLoader(dataroot=str(dataroot), version=VERSION, open_dataset=open_nuscenes)

    keyframes = await loader.load_keyframes()

    assert [k.image_path for k in keyframes] == [middle_image(0), middle_image(1)]
