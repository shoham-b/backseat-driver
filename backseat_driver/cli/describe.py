"""The describe command: read the scenes, process each image, write the descriptions.

It is the same three steps in both modes. `monolith` (the default) runs them in this process over a local dataset.
`distributed` hands the read and process steps to a running API and its workers, then writes what comes back.

Usage::

    backseat_driver describe --camera front --model Salesforce/blip-image-captioning-base
    backseat_driver describe --camera front --backend ollama --model llava:13b
    # -> output/ollama__llava-13b.json
    backseat_driver describe --all-cameras      # every scene from all six cameras
    backseat_driver describe --mode distributed --output output/cluster.json
"""

import sys
from typing import Annotated

import typer
from loguru import logger
from rich.progress import BarColumn, DownloadColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from backseat_driver.cli import app
from backseat_driver.cli.interruptible import run_interruptibly
from backseat_driver.config import RunMode, Settings, VlmBackend, get_settings
from backseat_driver.logger import LogFormat
from backseat_driver.models import Camera, Job, SceneDescription, SceneKeyframe
from backseat_driver.write.json_writer import write_json

_MONOLITH_ONLY = ("dataroot", "dataset_version", "camera", "all_cameras", "backend", "model")


def log_progress(index: int, total: int, keyframe: SceneKeyframe) -> None:
    logger.info("describing {} ({}) [{}/{}]", keyframe.scene_name, keyframe.camera_channel, index, total)


@app.command(rich_help_panel="Describe")
def describe(
    mode: Annotated[
        RunMode | None,
        typer.Option(
            help="monolith: run every step in this process. distributed: submit a job to the API and its workers "
            "[default: BACKSEAT_DRIVER_MODE]"
        ),
    ] = None,
    dataroot: Annotated[
        str | None, typer.Option(help="Monolith: cache directory for the nuScenes dataset (downloaded if missing)")
    ] = None,
    dataset_version: Annotated[
        str | None, typer.Option("--version", help="Monolith: nuScenes dataset version, e.g. v1.0-mini")
    ] = None,
    camera: Annotated[
        list[Camera] | None,
        typer.Option(
            help="Monolith: camera channel to use as the representative frame; repeat to describe several cameras"
        ),
    ] = None,
    all_cameras: Annotated[
        bool,
        typer.Option("--all-cameras", help="Monolith: describe all six cameras of every scene (instead of --camera)"),
    ] = False,
    backend: Annotated[
        VlmBackend | None,
        typer.Option(
            help="Monolith: captioner backend: huggingface (terse BLIP), ollama or anthropic (verbose, prompt-driven)"
        ),
    ] = None,
    model: Annotated[str | None, typer.Option(help="Monolith: model name for the chosen backend")] = None,
    output: Annotated[
        str | None,
        typer.Option(
            help="Where to write the JSON results [default: output/<backend>__<model>.json; required when distributed]"
        ),
    ] = None,
    max_scenes: Annotated[
        int | None, typer.Option(help="Only process the first N scenes (useful for a quick run)")
    ] = None,
    api_url: Annotated[
        str | None, typer.Option(help="Distributed: the API to submit the job to [default: the configured API]")
    ] = None,
    timeout: Annotated[
        float, typer.Option(help="Distributed: seconds to wait for the job to finish before failing")
    ] = 3600.0,
) -> None:
    """Describe every scene in the dataset and write results to a JSON file."""
    settings = get_settings()
    mode = mode or settings.mode
    given = {
        "dataroot": dataroot,
        "dataset_version": dataset_version,
        "camera": camera,
        "all_cameras": all_cameras,
        "backend": backend,
        "model": model,
    }

    if mode is RunMode.DISTRIBUTED:
        ignored = [f"--{name.replace('_', '-')}" for name in _MONOLITH_ONLY if given[name]]
        if ignored:
            raise typer.BadParameter(
                f"{', '.join(ignored)} only apply to --mode monolith: a distributed job uses the workers' own settings"
            )
        if output is None:
            raise typer.BadParameter("--output is required with --mode distributed: the model is chosen by the workers")
        descriptions = run_interruptibly(lambda: _describe_on_workers(api_url or settings.api_url, max_scenes, timeout))
    else:
        if all_cameras == bool(camera):
            raise typer.BadParameter("pass exactly one of --camera (repeatable) or --all-cameras")
        descriptions = run_interruptibly(
            lambda: _describe_here(
                settings, dataroot, dataset_version, camera or [], all_cameras, backend, model, max_scenes
            )
        )
        output = output or settings.output_path_for(backend, model)

    write_json(descriptions, output)
    logger.info("wrote {} scene description(s) to {}", len(descriptions), output)

    for d in descriptions:
        typer.echo(f"  {d.scene_name} [{d.camera_channel}]: {d.description}")


def _describe_here(
    settings: Settings,
    dataroot: str | None,
    version: str | None,
    camera: list[Camera],
    all_cameras: bool,
    backend: VlmBackend | None,
    model: str | None,
    max_scenes: int | None,
) -> list[SceneDescription]:
    """Rung 1 (see `stacks.pipeline`): the loader (read) and captioner (process) run in this process."""
    from backseat_driver.read.nuscenes_dataset import ensure_nuscenes_dataset
    from backseat_driver.read.nuscenes_scene_loader import ALL_CAMERA_CHANNELS
    from backseat_driver.stacks import pipeline as build_pipeline

    cameras = list(ALL_CAMERA_CHANNELS) if all_cameras else [c.channel for c in camera]
    dataroot = dataroot or settings.nuscenes_dataroot
    version = version or settings.nuscenes_version

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
    pipeline = build_pipeline(settings, dataroot, version, cameras, backend, model)

    logger.info("loading scenes from {!r} ({})", dataroot, version)
    if not interactive:
        return pipeline.run(max_scenes=max_scenes, on_progress=log_progress)
    with Progress(
        TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeRemainingColumn(), transient=True
    ) as progress:
        task = progress.add_task("starting")

        def advance(index: int, total: int, keyframe: SceneKeyframe) -> None:
            progress.update(
                task, total=total, completed=index - 1, description=f"{keyframe.scene_name} {keyframe.camera_channel}"
            )

        return pipeline.run(max_scenes=max_scenes, on_progress=advance)


def _describe_on_workers(api_url: str, max_scenes: int | None, timeout: float) -> list[SceneDescription]:
    """Distributed: the same steps run on the ingest and caption workers; this only submits the job and waits."""
    from backseat_driver.transport.api_client import ApiJobClient

    def log_job(job: Job) -> None:
        logger.info(
            "job {} is {} ({}/{} scenes)", job.job_id, job.state.value, job.completed_scenes, job.expected_scenes
        )

    logger.info("submitting a job to {}", api_url)
    return ApiJobClient(api_url).describe(max_scenes=max_scenes, timeout_seconds=timeout, on_progress=log_job)
