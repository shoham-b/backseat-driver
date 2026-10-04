"""`GET /images/{key}` over a real dataroot on disk."""

from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.app import create_app
from backseat_driver.api.dependencies import get_image_store
from backseat_driver.datasets.local_image_store import LocalImageStore
from tests.fakes import make_settings

KEY = "samples/CAM_FRONT/a.jpg"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    dataroot = tmp_path / "nuscenes"
    (dataroot / "samples" / "CAM_FRONT").mkdir(parents=True)
    (dataroot / KEY).write_bytes(b"jpeg bytes")
    (dataroot / "v1.0-mini").mkdir()
    (dataroot / "v1.0-mini" / "scene.json").write_text("[]")
    (tmp_path / "secret.jpg").write_bytes(b"not part of the dataset")
    app = create_app(make_settings())
    app.dependency_overrides[get_image_store] = lambda: LocalImageStore(str(dataroot))
    with TestClient(app) as test_client:
        yield test_client


def test_a_keyframe_image_is_served_with_its_type_and_caching_headers(client: TestClient) -> None:
    response = client.get(f"/images/{KEY}")

    assert response.status_code == HTTPStatus.OK
    assert response.content == b"jpeg bytes"
    assert response.headers["content-type"] == "image/jpeg"
    assert "immutable" in response.headers["cache-control"]
    assert response.headers["etag"]


def test_a_matching_if_none_match_gets_not_modified_without_a_body(client: TestClient) -> None:
    etag = client.get(f"/images/{KEY}").headers["etag"]

    response = client.get(f"/images/{KEY}", headers={"If-None-Match": etag})

    assert response.status_code == HTTPStatus.NOT_MODIFIED
    assert response.content == b""


def test_a_missing_image_is_not_found(client: TestClient) -> None:
    response = client.get("/images/samples/CAM_FRONT/missing.jpg")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_the_metadata_tables_are_not_served(client: TestClient) -> None:
    response = client.get("/images/v1.0-mini/scene.json")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_a_key_climbing_out_of_the_dataroot_cannot_read_other_files(client: TestClient) -> None:
    # The client collapses plain `..` segments, so send them encoded the way a hostile client would.
    response = client.get("/images/samples/%2e%2e/%2e%2e/secret.jpg")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert b"not part of the dataset" not in response.content
