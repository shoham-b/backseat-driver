import pytest

from backseat_driver.errors import NotFoundError, UnprocessableError
from backseat_driver.read.images.image_service import ImageService
from tests.fakes import FakeImageStore


def test_a_missing_image_is_reported_as_the_domains_not_found() -> None:
    # The fake hands out a path that does not exist, as a store does for a key nothing was uploaded under.
    service = ImageService(FakeImageStore())

    with pytest.raises(NotFoundError, match=r"samples/CAM_FRONT/a.jpg"):
        service.read("samples/CAM_FRONT/a.jpg")


@pytest.mark.parametrize("key", ["v1.0-mini/scene.json", "samples/../secret.jpg", "samples/CAM_FRONT/a.json"])
def test_a_key_that_is_not_a_keyframe_image_is_rejected_before_the_store_is_asked(key: str) -> None:
    store = FakeImageStore()

    with pytest.raises(UnprocessableError):
        ImageService(store).read(key)

    assert store.opened == []
