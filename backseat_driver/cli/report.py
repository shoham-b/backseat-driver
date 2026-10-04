"""Report command — compare how several models described the same scenes.

Usage::

    backseat_driver run --backend huggingface
    backseat_driver run --backend anthropic --model claude-haiku-4-5-20251001
    backseat_driver report          # every output/*.json -> output/report.html
"""

import json
import webbrowser
from pathlib import Path
from socket import socket
from typing import Annotated

import typer
import uvicorn
from loguru import logger

from backseat_driver.cli import app
from backseat_driver.config import get_settings
from backseat_driver.models import SceneDescription


@app.command()
def report(
    results: Annotated[
        list[Path] | None,
        typer.Argument(help="JSON files written by `run`; default: every *.json in the output directory"),
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


@app.command()
def ui(
    results: Annotated[
        list[Path] | None,
        typer.Argument(help="JSON files written by `run`; default: every *.json in the output directory"),
    ] = None,
    host: Annotated[str | None, typer.Option(help="Interface to serve on [default: BACKSEAT_DRIVER_UI_HOST]")] = None,
    port: Annotated[int | None, typer.Option(help="Port to serve on [default: BACKSEAT_DRIVER_UI_PORT]")] = None,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open the page in a browser")] = True,
    job: Annotated[
        list[str] | None,
        typer.Option(help="Completed job id to read from the API (repeatable; one job is one model's run)"),
    ] = None,
    all_jobs: Annotated[
        bool,
        typer.Option(
            "--all-jobs", help="Show every completed job on the API, re-read on each page load (newest per model)"
        ),
    ] = False,
    api_url: Annotated[
        str | None,
        typer.Option(
            help="API to read jobs and images from, and the live-inference card's target [default: configured]"
        ),
    ] = None,
    public_api_url: Annotated[
        str | None,
        typer.Option(
            help="Where the browser reaches the API for the live card, if not --api-url (e.g. a port-forward)"
        ),
    ] = None,
) -> None:
    """Serve the model-comparison UI: from result files, and/or from the API's jobs (rebuilt on every page load)."""
    from backseat_driver.reporting.api_source import ApiReportSource
    from backseat_driver.reporting.ui_server import ReportPage, create_ui_app

    settings = get_settings()
    host = host or settings.ui_host
    port = port or settings.ui_port
    results = results or ([] if job or all_jobs else _default_results())
    api_url = api_url or settings.api_url
    source = ApiReportSource(api_url) if job or all_jobs else None

    page = ReportPage(results, source, job, all_jobs, live_api_url=public_api_url or api_url)
    _, count = page.render()  # fail now, not on the first request, if a source is unreadable
    url = f"http://{host}:{port}/"
    logger.info("serving {} description(s) at {} (Ctrl+C to stop)", count, url)
    # log_config=None leaves uvicorn's loggers to the stdlib-to-loguru bridge; the access log would only be noise.
    config = uvicorn.Config(create_ui_app(page, source), host=host, port=port, log_config=None, access_log=False)
    _BrowserOpeningServer(config, url if open_browser else None).run()
    logger.info("stopped")


class _BrowserOpeningServer(uvicorn.Server):
    """Opens the page once the port is bound, so the browser never races the server."""

    def __init__(self, config: uvicorn.Config, open_url: str | None) -> None:
        super().__init__(config)
        self._open_url = open_url

    async def startup(self, sockets: list[socket] | None = None) -> None:
        await super().startup(sockets)
        if self._open_url and self.started:
            webbrowser.open(self._open_url)


def _default_results() -> list[Path]:
    found = sorted(Path(get_settings().output_dir).glob("*.json"))
    if not found:
        raise typer.BadParameter("no result files found; pass some or run `backseat-driver run` first")
    return found


def _write_report(
    results: list[Path],
    output: Path,
    api_url: str | None = None,
    jobs: list[str] | None = None,
    jobs_api_url: str | None = None,
) -> int:
    from backseat_driver.reporting.api_source import ApiReportSource
    from backseat_driver.reporting.html_report_writer import file_data_uri, write_html
    from backseat_driver.reporting.report import build_report

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
