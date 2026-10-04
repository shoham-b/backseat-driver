"""Dataset provisioning for the distributed mode.

Usage::

    backseat-driver dataset upload                  # the configured camera (BACKSEAT_DRIVER_CAMERA_CHANNEL)
    backseat-driver dataset upload --camera back
    backseat-driver dataset upload --all-cameras --dataroot data/sets/nuscenes
"""

from typing import Annotated

import typer

from backseat_driver.cli import dataset_app
from backseat_driver.config import get_settings
from backseat_driver.logger import LogFormat, setup_logging
from backseat_driver.models import Camera


@dataset_app.command()
def upload(
    dataroot: Annotated[str | None, typer.Option(help="Local nuScenes dataset to upload")] = None,
    version: Annotated[str | None, typer.Option(help="nuScenes dataset version, e.g. v1.0-mini")] = None,
    camera: Annotated[
        list[Camera] | None,
        typer.Option(help="Camera whose images to upload; repeat for several [default: the configured camera]"),
    ] = None,
    all_cameras: Annotated[
        bool, typer.Option("--all-cameras", help="Upload all six cameras (instead of --camera)")
    ] = False,
) -> None:
    """Upload the metadata tables and camera images the workers need to the dataset bucket."""
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="cli")

    from backseat_driver.datasets.factory import build_dataset_store
    from backseat_driver.datasets.uploader import DatasetUploader
    from backseat_driver.scenes.nuscenes_scene_loader import ALL_CAMERA_CHANNELS

    if all_cameras and camera:
        raise typer.BadParameter("pass --camera or --all-cameras, not both")
    # The workers only ever read the configured camera, so that is what is uploaded unless told otherwise.
    cameras = (
        list(ALL_CAMERA_CHANNELS)
        if all_cameras
        else [c.channel for c in camera]
        if camera
        else [settings.camera_channel]
    )

    result = DatasetUploader(build_dataset_store(settings)).upload(
        dataroot or settings.nuscenes_dataroot, version or settings.nuscenes_version, cameras
    )
    typer.secho(
        f"Uploaded {result.uploaded} file(s), skipped {result.skipped} already in the bucket", fg=typer.colors.GREEN
    )
