from pathlib import Path

import pytest

from backseat_driver.datasets.local_image_store import LocalImageStore


def test_the_uri_of_a_key_is_the_file_below_the_dataroot() -> None:
    store = LocalImageStore("/data/nu")

    assert Path(store.uri_for("samples/CAM_FRONT/a.jpg")) == Path("/data/nu/samples/CAM_FRONT/a.jpg").resolve()


@pytest.mark.parametrize("key", ["../secret.txt", "samples/../../secret.txt", "/etc/passwd"])
def test_a_key_that_leaves_the_dataroot_does_not_resolve(key: str) -> None:
    with pytest.raises(ValueError, match="outside the dataroot"):
        LocalImageStore("/data/nu").uri_for(key)


def test_local_copy_yields_the_same_path_without_copying() -> None:
    with LocalImageStore("/data/nu").local_copy("/data/nu/a.jpg") as path:
        assert path == Path("/data/nu/a.jpg")
