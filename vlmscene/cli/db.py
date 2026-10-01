"""Database commands for the distributed mode."""

from vlmscene.cli import db_app
from vlmscene.config import get_settings
from vlmscene.logger import LogFormat, setup_logging


@db_app.command()
def init() -> None:
    """Create the job tables if they don't exist (idempotent). Run once before starting the API and workers."""
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="db-init")

    from loguru import logger

    from vlmscene.adapters.postgres_job_store import PostgresJobStore

    PostgresJobStore(settings.database_url).ensure_schema()
    logger.info("database schema ready")
