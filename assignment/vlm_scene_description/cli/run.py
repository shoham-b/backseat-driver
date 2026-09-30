"""Main pipeline command — describe every scene in a nuScenes dataset.

Usage::

    vlm_scene_description run
    vlm_scene_description run --dataroot data/sets/nuscenes --version v1.0-mini \
        --camera CAM_FRONT --output output/scene_descriptions.json
"""

from typing import Annotated

import typer

from vlm_scene_description.cli import app
from vlm_scene_description.config import get_settings
from vlm_scene_description.logger import LogFormat, setup_logging


@app.command()
def run(
    dataroot: Annotated[str | None, typer.Option(help="Path to the local nuScenes dataset root")] = None,
    version: Annotated[str | None, typer.Option(help="nuScenes dataset version, e.g. v1.0-mini")] = None,
    camera: Annotated[str | None, typer.Option(help="Camera channel to use as the representative frame")] = None,
    model: Annotated[str | None, typer.Option(help="HuggingFace image-to-text model name")] = None,
    output: Annotated[str | None, typer.Option(help="Path to write the JSON results to")] = None,
    max_scenes: Annotated[
        int | None, typer.Option(help="Only process the first N scenes (useful for a quick run)")
    ] = None,
) -> None:
    """Describe every scene in the dataset and write results to a JSON file."""
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="cli")

    from vlm_scene_description.bl.captioner import BlipCaptioner
    from vlm_scene_description.bl.nuscenes_loader import NuScenesSceneLoader
    from vlm_scene_description.bl.pipeline import ScenePipeline
    from vlm_scene_description.bl.writer import write_json

    dataroot = dataroot or settings.nuscenes_dataroot
    version = version or settings.nuscenes_version
    camera = camera or settings.camera_channel
    model = model or settings.vlm_model_name
    output = output or settings.output_path

    loader = NuScenesSceneLoader(dataroot=dataroot, version=version, camera_channel=camera)
    captioner = BlipCaptioner(model_name=model)
    pipeline = ScenePipeline(loader=loader, captioner=captioner)

    typer.secho(f"Loading scenes from {dataroot!r} ({version})", fg=typer.colors.CYAN)
    descriptions = pipeline.run(max_scenes=max_scenes)

    write_json(descriptions, output)
    typer.secho(f"Wrote {len(descriptions)} scene description(s) to {output}", fg=typer.colors.GREEN)

    for d in descriptions:
        typer.echo(f"  {d.scene_name}: {d.description}")
