"""Builds the bucket-backed dataset store."""

from backseat_driver.config import Settings
from backseat_driver.read.s3.dataset_store import DatasetStore
from backseat_driver.read.s3.s3_dataset_store import S3DatasetStore


def build_dataset_store(settings: Settings) -> DatasetStore:
    if not settings.dataset_bucket:
        raise ValueError(
            "No dataset bucket chosen: set BACKSEAT_DRIVER_DATASET_BUCKET (and BACKSEAT_DRIVER_S3_ENDPOINT_URL for "
            "an S3-compatible store that isn't AWS)"
        )
    return S3DatasetStore(settings.dataset_bucket, settings.s3_endpoint_url)
