from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.app import create_app
from backseat_driver.api.dependencies import get_image_service
from backseat_driver.datasets.image_service import ImageService
from tests.fakes import FakeImageStore, make_settings


def _client() -> TestClient:
    app = create_app(make_settings())
    app.dependency_overrides[get_image_service] = lambda: ImageService(FakeImageStore())
    return TestClient(app)


@pytest.mark.parametrize(
    "key",
    [
        "v1.0-mini/scene.json",  # metadata, not an image
        "samples/CAM_FRONT/a.json",  # not an image suffix
        "samples/../v1.0-mini/a.jpg",  # climbs out of samples/
        "samples//a.jpg",
        "samples/CAM_FRONT%5Ca.jpg",  # a backslash
        "other/a.jpg",
    ],
)
def test_keys_that_are_not_keyframe_images_are_rejected_before_the_store_is_asked(key: str) -> None:
    with _client() as client:
        response = client.get(f"/images/{key}")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_the_validation_error_names_the_key() -> None:
    with _client() as client:
        response = client.get("/images/v1.0-mini/scene.json")

    assert "v1.0-mini/scene.json" in response.json()["error"]["message"]
