import typer

from vlm_scene_description.config import Settings as _Settings

app = typer.Typer(
    name="vlm_scene_description",
    help="Generates short natural-language scene descriptions for nuScenes driving scenes using a vision-language model",
    no_args_is_help=True,
)
client_app = typer.Typer(help="HTTP client for the items API", no_args_is_help=True)
demo_app = typer.Typer(help="Live demos of design patterns (no server needed)", no_args_is_help=True)
test_app = typer.Typer(help="Run test suites", no_args_is_help=True)
app.add_typer(client_app, name="client")
app.add_typer(demo_app, name="demo")
app.add_typer(test_app, name="test")

_s = _Settings()
_DEFAULT_API_URL: str = _s.api_url


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
) -> None:
    if version:
        from vlm_scene_description import __version__

        typer.echo(f"vlm_scene_description {__version__}")
        raise typer.Exit()
