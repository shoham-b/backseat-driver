import typer

app = typer.Typer(
    name="backseat-driver",
    help="Generates short natural-language scene descriptions for nuScenes scenes using a VLM",
    no_args_is_help=True,
)
test_app = typer.Typer(help="Run test suites", no_args_is_help=True)
app.add_typer(test_app, name="test")
worker_app = typer.Typer(help="Run a queue worker (distributed mode)", no_args_is_help=True)
app.add_typer(worker_app, name="worker")
db_app = typer.Typer(help="Database setup (distributed mode)", no_args_is_help=True)
app.add_typer(db_app, name="db")


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
    pass
