from pathlib import Path
from typing import Any

import pytest

from backseat_driver.read.s3.s3_dataset_store import S3DatasetStore


class _FakeS3Client:
    """Duck-types the slice of a boto3 S3 client these tests touch, recording each call."""

    def __init__(self, keys: list[str] | None = None) -> None:
        self.keys = keys or []
        self.uploads: list[tuple[str, str, str]] = []

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.uploads.append((filename, bucket, key))

    def list_objects_v2(self, Bucket: str, Prefix: str, MaxKeys: int) -> dict[str, Any]:
        return {"Contents": [{"Key": key} for key in self.keys if key.startswith(Prefix)][:MaxKeys]}


class _ClientBuilder:
    def __init__(self, client: _FakeS3Client | None = None) -> None:
        self.client = client or _FakeS3Client()
        self.endpoints: list[str | None] = []

    def __call__(self, endpoint_url: str | None) -> Any:
        self.endpoints.append(endpoint_url)
        return self.client


def test_the_uri_of_a_key_names_its_bucket() -> None:
    store = S3DatasetStore("nuscenes", make_client=_ClientBuilder())

    assert store.uri_for("samples/CAM_FRONT/a.jpg") == "s3://nuscenes/samples/CAM_FRONT/a.jpg"


def test_upload_sends_the_file_under_the_key() -> None:
    builder = _ClientBuilder()

    S3DatasetStore("nuscenes", make_client=builder).upload("samples/a.jpg", Path("/data/a.jpg"))

    assert builder.client.uploads == [(str(Path("/data/a.jpg")), "nuscenes", "samples/a.jpg")]


def test_exists_matches_the_exact_key_not_a_longer_one_sharing_its_prefix() -> None:
    store = S3DatasetStore("nuscenes", make_client=_ClientBuilder(_FakeS3Client(["samples/a.jpg.bak"])))

    assert not store.exists("samples/a.jpg")


def test_exists_finds_the_key() -> None:
    store = S3DatasetStore("nuscenes", make_client=_ClientBuilder(_FakeS3Client(["samples/a.jpg"])))

    assert store.exists("samples/a.jpg")


def test_the_client_is_built_on_first_use_with_the_endpoint_and_then_reused() -> None:
    builder = _ClientBuilder()
    store = S3DatasetStore("nuscenes", endpoint_url="http://s3:9090", make_client=builder)
    assert builder.endpoints == []

    store.upload("a.jpg", Path("a.jpg"))
    store.upload("b.jpg", Path("b.jpg"))

    assert builder.endpoints == ["http://s3:9090"]


@pytest.mark.parametrize("uri", ["/data/a.jpg", "s3://nuscenes", "s3://nuscenes/", "s3:///a.jpg", "http://x/a.jpg"])
def test_local_copy_rejects_uris_that_are_not_s3_objects(uri: str) -> None:
    builder = _ClientBuilder()
    store = S3DatasetStore("nuscenes", make_client=builder)

    with pytest.raises(ValueError, match="Not an S3 image URI"), store.local_copy(uri):
        pass

    assert builder.endpoints == []
