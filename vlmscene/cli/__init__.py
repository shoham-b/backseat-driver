import typer

app = typer.Typer(
    name="vlm-scene-description",
    help="Generates short natural-language scene descriptions for nuScenes scenes using a VLM",
    no_args_is_help=True,
)
test_app = typer.Typer(help="Run test suites", no_args_is_help=True)
app.add_typer(test_app, name="test")
worker_app = typer.Typer(help="Run a queue worker (distributed mode)", no_args_is_help=True)
app.add_typer(worker_app, name="worker")
db_app = typer.Typer(help="Database setup (distributed mode)", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
) -> None:
    if version:
        from vlmscene import __version__

        typer.echo(f"vlm-scene-description {__version__}")
        raise typer.Exit()
