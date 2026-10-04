"""Report command — compare how several models described the same scenes.

Usage::

    backseat_driver describe --backend huggingface
    backseat_driver describe --backend anthropic --model claude-haiku-4-5-20251001
    backseat_driver report          # every output/*.json -> output/report.html
"""

from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from backseat_driver.cli import app
from backseat_driver.config import get_settings


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
    count = _write_report(results, output, job or [], api_url or settings.api_url)
    logger.info("wrote report for {} description(s) to {}", count, output)


def _default_results() -> list[Path]:
    found = sorted(Path(get_settings().output_dir).glob("*.json"))
    if not found:
        raise typer.BadParameter("no result files found; pass some or run `backseat-driver describe` first")
    return found


def _write_report(results: list[Path], output: Path, jobs: list[str], api_url: str) -> int:
    from backseat_driver.show.api_source import ApiReportSource
    from backseat_driver.show.description_source import DescriptionSource
    from backseat_driver.show.html_report_writer import save_html
    from backseat_driver.show.report_service import ReportService
    from backseat_driver.show.result_file_source import ResultFileSource

    sources: list[DescriptionSource] = [ResultFileSource(results)]
    if jobs:
        sources.append(ApiReportSource(api_url, job_ids=jobs))
    rendered = ReportService(sources).render(embed_images=True)
    save_html(rendered.html, output)
    return rendered.description_count
