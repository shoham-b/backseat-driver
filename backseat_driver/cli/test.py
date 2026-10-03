"""Test-runner commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from backseat_driver.cli import test_app
from backseat_driver.cli.context import PytestNotInstalledError, cli_context

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# pytest's ExitCode.OK and NO_TESTS_COLLECTED; spelled out because pytest is only an (optional) dev dependency.
_SUCCESS_CODES = (0, 5)


@test_app.command()
def smoke(
    ctx: typer.Context,
    api_url: Annotated[
        str | None,
        typer.Option(envvar="API_URL", help="Base URL of a running service to test against"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run smoke tests against a running service.

    Defaults to http://localhost:8080. Start the service first:

        just infra && just dev   # local (the API's /ready checks RabbitMQ + Postgres)
        just compose up # containerised
    """
    args = [str(_PROJECT_ROOT / "tests" / "smoketests")]
    if verbose:
        args.append("-v")

    try:
        code = cli_context(ctx).run_pytest(args, api_url)
    except PytestNotInstalledError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    if code not in _SUCCESS_CODES:
        raise typer.Exit(code)
