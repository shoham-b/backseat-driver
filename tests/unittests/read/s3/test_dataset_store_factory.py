import pytest

from backseat_driver.read.s3.factory import build_dataset_store
from backseat_driver.read.s3.s3_dataset_store import S3DatasetStore
from tests.fakes import make_settings


def test_builds_an_s3_store_for_the_configured_bucket() -> None:
    store = build_dataset_store(make_settings(dataset_bucket="nuscenes", s3_endpoint_url="http://s3:9090"))

    assert isinstance(store, S3DatasetStore)


def test_a_missing_bucket_fails_fast_instead_of_picking_one() -> None:
    with pytest.raises(ValueError, match="BACKSEAT_DRIVER_DATASET_BUCKET"):
        build_dataset_store(make_settings())
