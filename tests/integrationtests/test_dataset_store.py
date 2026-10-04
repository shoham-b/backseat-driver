from pathlib import Path

import pytest

from backseat_driver.datasets.s3_dataset_store import S3DatasetStore
from backseat_driver.datasets.uploader import DatasetUploader
from tests.fakes import DiskS3Client, FakeDatasetStore


def _store(tmp_path: Path) -> S3DatasetStore:
    client = DiskS3Client(tmp_path / "buckets")
    return S3DatasetStore("nuscenes", make_client=lambda _endpoint: client)


def _file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_an_uploaded_image_is_readable_through_a_local_copy_that_is_removed_afterwards(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upload("samples/CAM_FRONT/a.jpg", _file(tmp_path / "a.jpg", b"jpeg bytes"))

    with store.local_copy(store.uri_for("samples/CAM_FRONT/a.jpg")) as copy:
        content, name = copy.read_bytes(), copy.name

    assert (content, name) == (b"jpeg bytes", "a.jpg")
    assert not copy.exists()


def test_the_local_copy_is_removed_when_the_caller_fails(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upload("k/a.jpg", _file(tmp_path / "a.jpg"))
    seen: list[Path] = []

    def use_then_fail() -> None:
        with store.local_copy(store.uri_for("k/a.jpg")) as copy:
            seen.append(copy)
            raise RuntimeError("model exploded")

    with pytest.raises(RuntimeError):
        use_then_fail()

    assert not seen[0].exists()


def test_exists_reports_uploaded_keys_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upload("samples/a.jpg", _file(tmp_path / "a.jpg"))

    assert (store.exists("samples/a.jpg"), store.exists("samples/b.jpg")) == (True, False)


def test_download_prefix_keeps_the_paths_below_the_prefix(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upload("v1.0-mini/scene.json", _file(tmp_path / "scene.json", b"[]"))
    store.upload("v1.0-mini/nested/log.json", _file(tmp_path / "log.json", b"{}"))
    store.upload("samples/a.jpg", _file(tmp_path / "a.jpg"))

    store.download_prefix("v1.0-mini/", tmp_path / "out")

    assert sorted(p.relative_to(tmp_path / "out").as_posix() for p in (tmp_path / "out").rglob("*") if p.is_file()) == [
        "nested/log.json",
        "scene.json",
    ]


def test_download_prefix_of_an_empty_prefix_says_the_dataset_was_not_uploaded(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="has the dataset been uploaded"):
        _store(tmp_path).download_prefix("v1.0-mini/", tmp_path / "out")


def _local_dataset(root: Path) -> Path:
    _file(root / "v1.0-mini" / "scene.json", b"[]")
    _file(root / "samples" / "CAM_FRONT" / "a.jpg")
    _file(root / "samples" / "CAM_BACK" / "b.jpg")
    _file(root / "sweeps" / "CAM_FRONT" / "sweep.jpg")
    _file(root / "maps" / "map.png")
    return root


def test_the_uploader_sends_the_tables_and_the_chosen_cameras_only(tmp_path: Path) -> None:
    store = FakeDatasetStore()

    result = DatasetUploader(store).upload(str(_local_dataset(tmp_path / "nu")), "v1.0-mini", ["CAM_FRONT"])

    assert sorted(store.objects) == ["samples/CAM_FRONT/a.jpg", "v1.0-mini/scene.json"]
    assert (result.uploaded, result.skipped) == (2, 0)


def test_rerunning_the_uploader_skips_images_already_there_but_replaces_the_tables(tmp_path: Path) -> None:
    store, dataroot = FakeDatasetStore(), str(_local_dataset(tmp_path / "nu"))
    uploader = DatasetUploader(store)
    uploader.upload(dataroot, "v1.0-mini", ["CAM_FRONT"])
    store.uploads.clear()

    result = uploader.upload(dataroot, "v1.0-mini", ["CAM_FRONT"])

    assert store.uploads == ["v1.0-mini/scene.json"]
    assert (result.uploaded, result.skipped) == (1, 1)


def test_the_uploader_fails_fast_when_the_version_has_no_tables(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"v1.0-mini"):
        DatasetUploader(FakeDatasetStore()).upload(str(tmp_path), "v1.0-mini", ["CAM_FRONT"])


class _ClientError(Exception):
    """Shaped like botocore's ClientError, which carries the S3 error code in `response`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FailingClient:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        raise self._error


@pytest.mark.parametrize("code", ["404", "NoSuchKey"])
def test_a_missing_object_is_reported_as_a_missing_file(code: str) -> None:
    store = S3DatasetStore("nuscenes", make_client=lambda _endpoint: _FailingClient(_ClientError(code)))

    with (
        pytest.raises(FileNotFoundError, match=r"s3://nuscenes/samples/a.jpg"),
        store.local_copy("s3://nuscenes/samples/a.jpg"),
    ):
        pass


def test_any_other_download_failure_is_not_mistaken_for_a_missing_file() -> None:
    store = S3DatasetStore("nuscenes", make_client=lambda _endpoint: _FailingClient(_ClientError("AccessDenied")))

    with pytest.raises(_ClientError), store.local_copy("s3://nuscenes/samples/a.jpg"):
        pass
