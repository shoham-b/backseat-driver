"""Main pipeline command — describe every scene in a nuScenes dataset.

Usage::

    backseat_driver run
    backseat_driver run --dataroot data/sets/nuscenes --version v1.0-mini \
        --camera CAM_FRONT --backend ollama --model llava:13b
    # -> output/ollama__llava-13b.json
"""

from typing import Annotated

import typer

from backseat_driver.cli import app
from backseat_driver.config import VlmBackend, get_settings
from backseat_driver.logger import LogFormat, setup_logging


@app.command()
def run(
    dataroot: Annotated[str | None, typer.Option(help="Path to the local nuScenes dataset root")] = None,
    version: Annotated[str | None, typer.Option(help="nuScenes dataset version, e.g. v1.0-mini")] = None,
    camera: Annotated[str | None, typer.Option(help="Camera channel to use as the representative frame")] = None,
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
    setup_logging(LogFormat(settings.log_format), service="cli")

    from backseat_driver.adapters.factory import build_captioner
    from backseat_driver.adapters.nuscenes_scene_loader import NuScenesSceneLoader
    from backseat_driver.bl.pipeline import ScenePipeline
    from backseat_driver.bl.writer import write_json

    dataroot = dataroot or settings.nuscenes_dataroot
    version = version or settings.nuscenes_version
    camera = camera or settings.camera_channel
    output = output or settings.output_path_for(backend, model)

    loader = NuScenesSceneLoader(dataroot=dataroot, version=version, camera_channel=camera)
    captioner = build_captioner(settings, backend=backend, model_name=model)
    pipeline = ScenePipeline(loader=loader, captioner=captioner)

    typer.secho(f"Loading scenes from {dataroot!r} ({version})", fg=typer.colors.CYAN)
    descriptions = pipeline.run(max_scenes=max_scenes)

    write_json(descriptions, output)
    typer.secho(f"Wrote {len(descriptions)} scene description(s) to {output}", fg=typer.colors.GREEN)

    for d in descriptions:
        typer.echo(f"  {d.scene_name}: {d.description}")
