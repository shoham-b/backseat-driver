"""Main pipeline command — describe every scene in a nuScenes dataset.

Usage::

    backseat_driver run
    backseat_driver run --dataroot data/sets/nuscenes --version v1.0-mini \
        --camera CAM_FRONT --backend ollama --model llava:13b
    # -> output/ollama__llava-13b.json
    backseat_driver run --all-cameras      # every scene from all six cameras
"""

import sys
from typing import Annotated

import typer
from loguru import logger
from rich.progress import BarColumn, DownloadColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from backseat_driver.cli import app
from backseat_driver.config import VlmBackend, get_settings
from backseat_driver.logger import LogFormat
from backseat_driver.models import SceneKeyframe


def log_progress(index: int, total: int, keyframe: SceneKeyframe) -> None:
    logger.info("describing {} ({}) [{}/{}]", keyframe.scene_name, keyframe.camera_channel, index, total)


@app.command()
def run(
    dataroot: Annotated[
        str | None, typer.Option(help="Cache directory for the nuScenes dataset (downloaded here if missing)")
    ] = None,
    version: Annotated[str | None, typer.Option(help="nuScenes dataset version, e.g. v1.0-mini")] = None,
    camera: Annotated[
        list[str] | None,
        typer.Option(help="Camera channel to use as the representative frame; repeat to describe several cameras"),
    ] = None,
    all_cameras: Annotated[
        bool, typer.Option("--all-cameras", help="Describe all six cameras of every scene (instead of --camera)")
    ] = False,
    backend: Annotated[
        VlmBackend | None,
        typer.Option(help="Captioner backend: huggingface (terse BLIP), ollama or anthropic (verbose, prompt-driven)"),
    ] = None,
    model: Annotated[str | None, typer.Option(help="Model name for the chosen backend")] = None,
    output: Annotated[
        str | None, typer.Option(help="Where to write the JSON results [default: output/<backend>__<model>.json]")
    ] = None,
    max_scenes: Annotated[
        int | None, typer.Option(help="Only process the first N scenes (useful for a quick run)")
    ] = None,
) -> None:
    """Describe every scene in the dataset and write results to a JSON file."""
    settings = get_settings()

    from backseat_driver.captioning.factory import build_captioner
    from backseat_driver.scenes.nuscenes_dataset import ensure_nuscenes_dataset
    from backseat_driver.scenes.nuscenes_scene_loader import ALL_CAMERA_CHANNELS, NuScenesSceneLoader
    from backseat_driver.scenes.pipeline import ScenePipeline
    from backseat_driver.scenes.writer import write_json

    if all_cameras == bool(camera):
        raise typer.BadParameter("pass exactly one of --camera (repeatable) or --all-cameras")
    cameras = list(ALL_CAMERA_CHANNELS) if all_cameras else camera or []

    dataroot = dataroot or settings.nuscenes_dataroot
    version = version or settings.nuscenes_version
    output = output or settings.output_path_for(backend, model)

    # A moving bar would garble piped output and JSON logs, so those get log lines instead.
    interactive = settings.log_format == LogFormat.COLORED and sys.stderr.isatty()

    if interactive:
        with Progress(
            TextColumn("nuScenes download"), BarColumn(), DownloadColumn(), TimeRemainingColumn(), transient=True
        ) as downloads:
            task = downloads.add_task("download", total=None)

            def advance_download(downloaded: int, total: int | None) -> None:
                downloads.update(task, total=total, completed=downloaded)

            ensure_nuscenes_dataset(dataroot, version, settings.nuscenes_url, on_progress=advance_download)
    else:
        ensure_nuscenes_dataset(dataroot, version, settings.nuscenes_url)
    loader = NuScenesSceneLoader(dataroot=dataroot, version=version, camera_channels=cameras)
    captioner = build_captioner(settings, backend=backend, model_name=model)
    pipeline = ScenePipeline(loader=loader, captioner=captioner)

    logger.info("loading scenes from {!r} ({})", dataroot, version)
    if interactive:
        with Progress(
            TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeRemainingColumn(), transient=True
        ) as progress:
            task = progress.add_task("starting")

            def advance(index: int, total: int, keyframe: SceneKeyframe) -> None:
                progress.update(
                    task,
                    total=total,
                    completed=index - 1,
                    description=f"{keyframe.scene_name} {keyframe.camera_channel}",
                )

            descriptions = pipeline.run(max_scenes=max_scenes, on_progress=advance)
    else:
        descriptions = pipeline.run(max_scenes=max_scenes, on_progress=log_progress)

    write_json(descriptions, output)
    logger.info("wrote {} scene description(s) to {}", len(descriptions), output)

    for d in descriptions:
        typer.echo(f"  {d.scene_name} [{d.camera_channel}]: {d.description}")
