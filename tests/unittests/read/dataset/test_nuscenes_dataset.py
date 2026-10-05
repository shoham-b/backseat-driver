import os
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from loguru import logger

from backseat_driver.read.dataset.nuscenes_dataset import LogEveryTenPercent, ensure_nuscenes_dataset


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
    # file:// archives are told apart by Last-Modified (1s resolution) and size; two files written back to back can tie.
    stamp = newer.stat().st_mtime + 60
    os.utime(newer, (stamp, stamp))

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


def test_download_reports_progress_to_the_callback(tmp_path: Path) -> None:
    url = _archive(tmp_path, "v1.0-mini/a.json").as_uri()
    seen: list[tuple[int, int | None]] = []

    ensure_nuscenes_dataset(str(tmp_path / "cache"), "v1.0-mini", url, on_progress=lambda *args: seen.append(args))

    assert seen
    assert seen[-1][0] == seen[-1][1]


def test_the_default_progress_logs_each_ten_percent_once() -> None:
    messages: list[str] = []
    sink = logger.add(messages.append, format="{message}")
    progress = LogEveryTenPercent()

    try:
        for downloaded in (5, 25, 26, 100):
            progress(downloaded, 100)
    finally:
        logger.remove(sink)

    assert [m.strip() for m in messages] == [f"nuScenes download {percent}%" for percent in range(10, 101, 10)]


def test_the_default_progress_stays_quiet_when_the_total_is_unknown() -> None:
    messages: list[str] = []
    sink = logger.add(messages.append, format="{message}")

    try:
        LogEveryTenPercent()(500, None)
    finally:
        logger.remove(sink)

    assert messages == []


@contextmanager
def _undeletable(directory: Path) -> Iterator[None]:
    """Make removing what is inside `directory` fail: a locked file on Windows, a read-only directory elsewhere."""
    if os.name == "nt":
        with (directory / "stale").open("rb"):  # an open handle blocks deletion on Windows
            yield
        return
    directory.chmod(0o500)
    try:
        yield
    finally:
        directory.chmod(0o700)


@pytest.mark.skipif(os.name != "nt" and os.geteuid() == 0, reason="root can delete from a read-only directory")
def test_a_cache_that_cannot_be_cleared_is_an_error_not_a_reason_to_download_over_it(tmp_path: Path) -> None:
    url = _archive(tmp_path, "v1.0-mini/scene.json").as_uri()
    dataroot = tmp_path / "cache"
    stale = dataroot / "v1.0-mini"
    stale.mkdir(parents=True)
    (stale / "stale").write_text("old")

    with _undeletable(stale), pytest.raises(PermissionError):
        ensure_nuscenes_dataset(str(dataroot), "v1.0-mini", url)

    assert not (dataroot / ".nuscenes-cache.json").exists()
