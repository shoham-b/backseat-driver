"""Report command — compare how several models described the same scenes.

Usage::

    backseat_driver run --backend huggingface --output output/blip.json
    backseat_driver run --backend anthropic --output output/claude.json
    backseat_driver report output/blip.json output/claude.json --output output/report.html
"""

import json
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
    from backseat_driver.adapters.html_report_writer import write_html
    from backseat_driver.bl.report import build_report

    descriptions = [
        SceneDescription.model_validate(item)
        for path in results
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    write_html(build_report(descriptions), str(output))
    typer.secho(f"Wrote report for {len(descriptions)} description(s) to {output}", fg=typer.colors.GREEN)
