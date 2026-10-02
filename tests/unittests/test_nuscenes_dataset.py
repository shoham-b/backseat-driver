import tarfile
from pathlib import Path

import pytest

from backseat_driver.scenes.nuscenes_dataset import ensure_nuscenes_dataset


def _archive(tmp_path: Path, *members: str) -> Path:
    source = tmp_path / "src"
    for member in members:
        (source / member).parent.mkdir(parents=True, exist_ok=True)
        (source / member).write_text("x")
    archive = tmp_path / "dataset.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        for entry in source.iterdir():
            tar.add(entry, arcname=entry.name)
    return archive


def test_downloads_and_extracts_into_an_empty_cache(tmp_path: Path) -> None:
    url = _archive(tmp_path, "v1.0-mini/scene.json", "samples/CAM_FRONT/a.jpg").as_uri()
    dataroot = tmp_path / "cache"

    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", url)

    assert (dataroot / "v1.0-mini" / "scene.json").exists()
    assert (dataroot / "samples" / "CAM_FRONT" / "a.jpg").exists()
    assert not (dataroot / ".download").exists()


def test_a_valid_cache_is_left_untouched(tmp_path: Path) -> None:
    url = _archive(tmp_path, "v1.0-mini/scene.json").as_uri()
    dataroot = tmp_path / "cache"
    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", url)
    sentinel = dataroot / "v1.0-mini" / "sentinel"
    sentinel.write_text("kept")

    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", url)

    assert sentinel.exists()


def test_a_cache_without_the_marker_is_replaced(tmp_path: Path) -> None:
    url = _archive(tmp_path, "v1.0-mini/scene.json").as_uri()
    dataroot = tmp_path / "cache"
    (dataroot / "v1.0-mini").mkdir(parents=True)  # e.g. an interrupted or hand-made extraction

    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", url)

    assert (dataroot / "v1.0-mini" / "scene.json").exists()


def test_a_cache_from_an_older_archive_is_replaced(tmp_path: Path) -> None:
    old_url = _archive(tmp_path, "v1.0-mini/old.json").as_uri()
    dataroot = tmp_path / "cache"
    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", old_url)
    newer = tmp_path / "dataset.tgz"
    with tarfile.open(newer, "w:gz") as tar:
        (tmp_path / "new.json").write_text("a longer payload so the size differs")
        tar.add(tmp_path / "new.json", arcname="v1.0-mini/new.json")

    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", old_url)

    assert (dataroot / "v1.0-mini" / "new.json").exists()
    assert not (dataroot / "v1.0-mini" / "old.json").exists()


def test_raises_when_archive_lacks_the_version_dir(tmp_path: Path) -> None:
    url = _archive(tmp_path, "samples/a.jpg").as_uri()

    with pytest.raises(RuntimeError, match=r"v1.0-mini"):
        ensure_nuscenes_dataset(str(tmp_path / "cache"), "v1.0-mini", url)


def test_an_unreachable_server_is_an_error_even_with_a_cache(tmp_path: Path) -> None:
    dataroot = tmp_path / "cache"
    ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", _archive(tmp_path, "v1.0-mini/a.json").as_uri())

    with pytest.raises(OSError, match=r"gone.tgz"):
        ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", (tmp_path / "gone.tgz").as_uri())
