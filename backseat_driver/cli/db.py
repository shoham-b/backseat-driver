"""Database commands for the distributed mode."""

import asyncio
from contextlib import aclosing

from backseat_driver.cli import db_app
from backseat_driver.config import get_settings
from backseat_driver.logger import LogFormat, setup_logging


@db_app.command()
def init() -> None:
    """Create the job tables if they don't exist (idempotent). Run once before starting the API and workers."""
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="db-init")

    from loguru import logger

    from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
    from backseat_driver.write.job_store.storage import JobStorage

    async def create_tables() -> None:
        # Its connections belong to this loop, which ends with the command, so close them before it does.
        async with aclosing(SqlJobStore(JobStorage(settings.database_url))) as store:
            await store.ensure_schema()

    asyncio.run(create_tables())
    logger.info("database schema ready")
