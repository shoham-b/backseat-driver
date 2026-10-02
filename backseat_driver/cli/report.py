"""Report command — compare how several models described the same scenes.

Usage::

    backseat_driver run --backend huggingface
    backseat_driver run --backend anthropic --model claude-haiku-4-5-20251001
    backseat_driver report          # every output/*.json -> output/report.html
"""

import functools
import http.server
import json
import tempfile
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from backseat_driver.cli import app
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
) -> None:
    """Build an HTML report: scenes, each model's description, filters, and accuracy metrics."""
    from backseat_driver.config import get_settings

    output = output or Path(get_settings().output_dir) / "report.html"
    results = results or _default_results()
    count = _write_report(results, output)
    typer.secho(f"Wrote report for {count} description(s) to {output}", fg=typer.colors.GREEN)


@app.command()
def ui(
    results: Annotated[
        list[Path] | None,
        typer.Argument(help="JSON files written by `run`; default: every *.json in the output directory"),
    ] = None,
    host: Annotated[str | None, typer.Option(help="Interface to serve on [default: BACKSEAT_DRIVER_UI_HOST]")] = None,
    port: Annotated[int | None, typer.Option(help="Port to serve on [default: BACKSEAT_DRIVER_UI_PORT]")] = None,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open the page in a browser")] = True,
    api_url: Annotated[
        str | None, typer.Option(help="API serving /describe for the live-inference card (default: the configured API)")
    ] = None,
) -> None:
    """Serve the model-comparison UI locally (rebuilt from the result files on every start)."""
    from backseat_driver.config import get_settings

    settings = get_settings()
    host = host or settings.ui_host
    port = port or settings.ui_port
    results = results or _default_results()
    api_url = api_url or settings.api_url

    with tempfile.TemporaryDirectory() as tmp:
        count = _write_report(results, Path(tmp) / "index.html", api_url)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
        url = f"http://{host}:{port}/"
        typer.secho(f"Serving {count} description(s) from {len(results)} file(s) at {url} (Ctrl+C to stop)", fg="green")
        with http.server.ThreadingHTTPServer((host, port), handler) as server:
            if open_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                typer.echo("Stopped")


def _default_results() -> list[Path]:
    from backseat_driver.config import get_settings

    found = sorted(Path(get_settings().output_dir).glob("*.json"))
    if not found:
        raise typer.BadParameter("no result files found; pass some or run `backseat-driver run` first")
    return found


def _write_report(results: list[Path], output: Path, api_url: str | None = None) -> int:
    from backseat_driver.reporting.html_report_writer import write_html
    from backseat_driver.reporting.report import build_report

    descriptions = [
        SceneDescription.model_validate(item)
        for path in results
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    write_html(build_report(descriptions), str(output), api_url)
    return len(descriptions)
