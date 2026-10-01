from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from vlmscene.api.errors import APIError
from vlmscene.api.exception_handlers import (
    api_error_handler,
    domain_error_handler,
    unhandled_exception_handler,
)
from vlmscene.api.middleware import RequestIDMiddleware
from vlmscene.api.routers.describe import router as describe_router
from vlmscene.api.routers.health import router as health_router
from vlmscene.api.routers.jobs import router as jobs_router
from vlmscene.bl.captioner import BlipCaptioner
from vlmscene.bl.errors import DomainError
from vlmscene.bl.job_queue import CeleryJobQueue
from vlmscene.bl.job_store import PostgresJobStore
from vlmscene.config import get_settings
from vlmscene.logger import LogFormat, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="api")

    app.state.settings = settings
    app.state.captioner = BlipCaptioner(model_name=settings.vlm_model_name)
    # Neither client connects until first use, so startup never blocks on the broker or database;
    # /ready reports whether they are reachable.
    app.state.job_queue = CeleryJobQueue(settings.rabbitmq_url)
    app.state.job_store = PostgresJobStore(settings.database_url)

    logger.bind(api_url=settings.api_url).info("startup complete")
    yield

    logger.info("shutdown")


app = FastAPI(title="VLM Scene Description", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore
app.add_exception_handler(APIError, api_error_handler)  # type: ignore
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(health_router)
app.include_router(describe_router)
app.include_router(jobs_router)
