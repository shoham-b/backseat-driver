from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

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
from backseat_driver.captioning.factory import build_captioner
from backseat_driver.config import get_settings
from backseat_driver.errors import DomainError
from backseat_driver.jobs.factory import build_job_backend
from backseat_driver.logger import LogFormat, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="api")

    app.state.settings = settings
    app.state.captioner = build_captioner(settings)
    # In distributed mode neither client connects until first use, so startup never blocks on the broker
    # or database; /ready reports whether they are reachable.
    app.state.job_queue, app.state.job_store = build_job_backend(settings, app.state.captioner)

    logger.bind(api_url=settings.api_url, mode=settings.mode).info("startup complete")
    yield

    logger.info("shutdown")


app = FastAPI(title="Backseat Driver", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
# Middleware is built at import time, before the lifespan runs, so settings are read here.
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["GET", "POST"])
app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore
app.add_exception_handler(APIError, api_error_handler)  # type: ignore
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(health_router)
app.include_router(describe_router)
app.include_router(jobs_router)
