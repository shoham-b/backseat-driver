"""Builds the store that carries keyframe images: the bucket when distributed, the local dataroot otherwise."""

from backseat_driver.config import RunMode, Settings
from backseat_driver.datasets.dataset_store import DatasetStore
from backseat_driver.datasets.image_store import ImageStore
from backseat_driver.datasets.local_image_store import LocalImageStore
from backseat_driver.datasets.s3_dataset_store import S3DatasetStore


def build_dataset_store(settings: Settings) -> DatasetStore:
    if not settings.dataset_bucket:
        raise ValueError(
            "No dataset bucket chosen: set BACKSEAT_DRIVER_DATASET_BUCKET (and BACKSEAT_DRIVER_S3_ENDPOINT_URL for "
            "an S3-compatible store that isn't AWS)"
        )
    return S3DatasetStore(settings.dataset_bucket, settings.s3_endpoint_url)


def build_image_store(settings: Settings) -> ImageStore:
    """The store for `settings.mode`: the local dataroot in the monolith, the bucket when distributed."""
    if settings.mode is RunMode.MONOLITH:
        return LocalImageStore(settings.nuscenes_dataroot)
    return build_dataset_store(settings)
