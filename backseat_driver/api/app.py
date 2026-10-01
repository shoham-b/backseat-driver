from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from backseat_driver.adapters.celery_job_queue import CeleryJobQueue
from backseat_driver.adapters.factory import build_captioner
from backseat_driver.adapters.postgres.job_store import PostgresJobStore
from backseat_driver.api.errors import APIError
from backseat_driver.api.exception_handlers import (
    api_error_handler,
    domain_error_handler,
    unhandled_exception_handler,
)
from backseat_driver.api.middleware import RequestIDMiddleware
from backseat_driver.api.routers.describe import router as describe_router
from backseat_driver.api.routers.health import router as health_router
from backseat_driver.api.routers.jobs import router as jobs_router
from backseat_driver.bl.errors import DomainError
from backseat_driver.config import get_settings
from backseat_driver.logger import LogFormat, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="api")

    app.state.settings = settings
    app.state.captioner = build_captioner(settings)
    # Neither client connects until first use, so startup never blocks on the broker or database;
    # /ready reports whether they are reachable.
    app.state.job_queue = CeleryJobQueue(settings.rabbitmq_url)
    app.state.job_store = PostgresJobStore(settings.database_url)

    logger.bind(api_url=settings.api_url).info("startup complete")
    yield

    logger.info("shutdown")


app = FastAPI(title="Backseat Driver", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore
app.add_exception_handler(APIError, api_error_handler)  # type: ignore
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(health_router)
app.include_router(describe_router)
app.include_router(jobs_router)
