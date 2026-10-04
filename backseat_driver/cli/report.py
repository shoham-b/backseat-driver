"""Report command — compare how several models described the same scenes.

Usage::

    backseat_driver describe --backend huggingface
    backseat_driver describe --backend anthropic --model claude-haiku-4-5-20251001
    backseat_driver report          # every output/*.json -> output/report.html
"""

import json
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from backseat_driver.cli import app
from backseat_driver.config import get_settings
from backseat_driver.models import SceneDescription


@app.command(rich_help_panel="Show")
def report(
    results: Annotated[
        list[Path] | None,
        typer.Argument(help="JSON files written by `describe`; default: every *.json in the output directory"),
    ] = None,
    output: Annotated[
        Path | None, typer.Option(help="Where to write the HTML report (default: <output dir>/report.html)")
    ] = None,
    job: Annotated[
        list[str] | None,
        typer.Option(help="Completed job id to read from the API (repeatable; one job is one model's run)"),
    ] = None,
    api_url: Annotated[str | None, typer.Option(help="API to read --job from [default: the configured API]")] = None,
) -> None:
    """Build an HTML report: scenes, each model's description, filters, and accuracy metrics."""
    settings = get_settings()
    output = output or Path(settings.output_dir) / "report.html"
    results = results or ([] if job else _default_results())
    count = _write_report(results, output, jobs=job or [], jobs_api_url=api_url or settings.api_url)
    logger.info("wrote report for {} description(s) to {}", count, output)


def _default_results() -> list[Path]:
    found = sorted(Path(get_settings().output_dir).glob("*.json"))
    if not found:
        raise typer.BadParameter("no result files found; pass some or run `backseat-driver describe` first")
    return found


def _write_report(
    results: list[Path],
    output: Path,
    api_url: str | None = None,
    jobs: list[str] | None = None,
    jobs_api_url: str | None = None,
) -> int:
    from backseat_driver.show.api_source import ApiReportSource
    from backseat_driver.show.html_report_writer import file_data_uri, write_html
    from backseat_driver.show.report import build_report

    descriptions = [
        SceneDescription.model_validate(item)
        for path in results
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    source = ApiReportSource(jobs_api_url or "")
    api_images: set[str] = set()
    for job_id in jobs or []:
        job_descriptions = source.descriptions(job_id)
        api_images.update(d.image_path for d in job_descriptions)
        descriptions += job_descriptions

    def read_image(image_path: str) -> str:
        # A job's image_path is a dataset key the API serves; a result file's is a local path.
        return source.image(image_path) if image_path in api_images else file_data_uri(image_path)

    write_html(build_report(descriptions), str(output), api_url, read_image)
    return len(descriptions)
