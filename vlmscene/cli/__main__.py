from vlmscene.cli import app
from vlmscene.cli import db as _db  # noqa: F401 — registers db subcommands
from vlmscene.cli import run as _run  # noqa: F401 — registers the run command
from vlmscene.cli import test as _test  # noqa: F401 — registers test subcommands
from vlmscene.cli import worker as _worker  # noqa: F401 — registers worker subcommands

if __name__ == "__main__":
    app()
