from vlm_scene_description.cli import app
from vlm_scene_description.cli import client as _client  # noqa: F401 — registers client subcommands
from vlm_scene_description.cli import demo as _demo  # noqa: F401 — registers demo subcommands
from vlm_scene_description.cli import test as _test  # noqa: F401 — registers test subcommands

if __name__ == "__main__":
    app()
