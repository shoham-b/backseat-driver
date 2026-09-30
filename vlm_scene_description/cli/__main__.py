from vlm_scene_description.cli import app
from vlm_scene_description.cli import run as _run  # noqa: F401 — registers the run command
from vlm_scene_description.cli import test as _test  # noqa: F401 — registers test subcommands

if __name__ == "__main__":
    app()
