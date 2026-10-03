"""Database commands for the distributed mode."""

import typer
from loguru import logger

from backseat_driver.cli import db_app
from backseat_driver.cli.context import cli_context
from backseat_driver.logger import LogFormat


@db_app.command()
def init(ctx: typer.Context) -> None:
    """Create the job tables if they don't exist (idempotent). Run once before starting the API and workers."""
    deps = cli_context(ctx)
    deps.configure_logging(LogFormat(deps.settings.log_format), "db-init")

    deps.init_schema(deps.settings.database_url)
    logger.info("database schema ready")
