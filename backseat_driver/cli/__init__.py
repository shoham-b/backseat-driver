import typer

from backseat_driver.config import get_settings
from backseat_driver.logger import LogFormat, setup_logging

app = typer.Typer(
    name="backseat-driver",
    help="Generates short natural-language scene descriptions for nuScenes scenes using a VLM. "
    "`describe` runs read -> process -> write; `report` shows the results (`just ui` serves them).",
    no_args_is_help=True,
)
test_app = typer.Typer(help="Run test suites", no_args_is_help=True)
app.add_typer(test_app, name="test", rich_help_panel="Development")
worker_app = typer.Typer(help="Run a queue worker (distributed mode)", no_args_is_help=True)
app.add_typer(worker_app, name="worker", rich_help_panel="Scale out (distributed mode)")
db_app = typer.Typer(help="Database setup (distributed mode)", no_args_is_help=True)
app.add_typer(db_app, name="db", rich_help_panel="Scale out (distributed mode)")
dataset_app = typer.Typer(help="Dataset provisioning (distributed mode)", no_args_is_help=True)
app.add_typer(dataset_app, name="dataset", rich_help_panel="Scale out (distributed mode)")


def _print_version(value: bool) -> None:
    if value:
        from backseat_driver import __version__

        typer.echo(f"backseat-driver {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    # Eager, so the flag is handled while parsing: otherwise click reports "Missing command" before the callback runs.
    version: bool = typer.Option(
        False, "--version", "-V", callback=_print_version, is_eager=True, help="Show version and exit"
    ),
) -> None:
    # Workers and `db init` call this again with their own service name.
    setup_logging(LogFormat(get_settings().log_format), service="cli")
