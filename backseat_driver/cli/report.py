"""Report command — compare how several models described the same scenes.

Usage::

    backseat_driver run --backend huggingface --output output/blip.json
    backseat_driver run --backend anthropic --output output/claude.json
    backseat_driver report output/blip.json output/claude.json --output output/report.html
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
    results: Annotated[list[Path], typer.Argument(help="JSON files written by `run`, one per model")],
    output: Annotated[Path, typer.Option(help="Where to write the self-contained HTML report")] = Path(
        "output/report.html"
    ),
) -> None:
    """Build an HTML report: scenes, each model's description, filters, and accuracy metrics."""
    count = _write_report(results, output)
    typer.secho(f"Wrote report for {count} description(s) to {output}", fg=typer.colors.GREEN)


@app.command()
def ui(
    results: Annotated[
        list[Path] | None,
        typer.Argument(help="JSON files written by `run`; default: every *.json beside the configured output path"),
    ] = None,
    host: Annotated[str, typer.Option(help="Interface to serve on")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to serve on")] = 8081,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open the page in a browser")] = True,
) -> None:
    """Serve the model-comparison UI locally (rebuilt from the result files on every start)."""
    from backseat_driver.config import get_settings

    if not results:
        results = sorted(Path(get_settings().output_path).parent.glob("*.json"))
        if not results:
            raise typer.BadParameter("no result files found; pass some or run `backseat-driver run` first")

    with tempfile.TemporaryDirectory() as tmp:
        count = _write_report(results, Path(tmp) / "index.html")
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


def _write_report(results: list[Path], output: Path) -> int:
    from backseat_driver.adapters.html_report_writer import write_html
    from backseat_driver.bl.report import build_report

    descriptions = [
        SceneDescription.model_validate(item)
        for path in results
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    write_html(build_report(descriptions), str(output))
    return len(descriptions)
