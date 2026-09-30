"""Test-runner commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from vlmscene.cli import test_app

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@test_app.command()
def smoke(
    api_url: Annotated[
        str | None,
        typer.Option(envvar="API_URL", help="Base URL of a running service to test against"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run smoke tests against a running service.

    Defaults to http://localhost:8080. Start the service first:

        just dev          # local
        docker compose up # containerised
    """
    try:
        import pytest
    except ImportError:
        typer.echo("pytest is not installed — run: uv sync --group dev", err=True)
        raise typer.Exit(1) from None

    if api_url:
        os.environ["API_URL"] = api_url

    args = [str(_PROJECT_ROOT / "tests" / "smoketests")]
    if verbose:
        args.append("-v")

    result = pytest.main(args)
    if result not in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        raise typer.Exit(int(result))
