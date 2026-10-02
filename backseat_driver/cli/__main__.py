from backseat_driver.cli import app
from backseat_driver.cli import db as _db  # noqa: F401 — registers db subcommands
from backseat_driver.cli import report as _report  # noqa: F401 — registers the report command
from backseat_driver.cli import run as _run  # noqa: F401 — registers the run command
from backseat_driver.cli import test as _test  # noqa: F401 — registers test subcommands
from backseat_driver.cli import worker as _worker  # noqa: F401 — registers worker subcommands

if __name__ == "__main__":
    app()
