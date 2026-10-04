from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backseat_driver.api.errors import APIError
from backseat_driver.api.exception_handlers import (
    api_error_handler,
    backseat_driver_error_handler,
    unhandled_exception_handler,
)
from backseat_driver.api.middleware import RequestIDMiddleware
from backseat_driver.api.routers.describe import router as describe_router
from backseat_driver.api.routers.health import router as health_router
from backseat_driver.api.routers.jobs import router as jobs_router
from backseat_driver.captioning.factory import build_captioner
from backseat_driver.config import Settings, get_settings
from backseat_driver.datasets.factory import build_image_store
from backseat_driver.errors import BackseatDriverError
from backseat_driver.jobs.factory import build_job_backend
from backseat_driver.logger import LogFormat, setup_logging


def create_app(settings: Settings) -> FastAPI:
    """Build the service for `settings`; tests build their own with `dependency_overrides` instead of patching."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        setup_logging(LogFormat(settings.log_format), service="api")

        app.state.settings = settings
        app.state.captioner = build_captioner(settings)
        # The local dataroot in the monolith; in distributed mode the bucket, which a distributed API must be configured
        # with. Either way the store is only built here, not connected.
        images = build_image_store(settings)
        # In distributed mode neither client connects until first use, so startup never blocks on the broker
        # or database; /ready reports whether they are reachable.
        app.state.job_queue, app.state.job_store = build_job_backend(settings, app.state.captioner, images)

        logger.bind(api_url=settings.api_url, mode=settings.mode).info("startup complete")
        yield

        logger.info("shutdown")

    app = FastAPI(title="Backseat Driver", lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"])
    app.add_exception_handler(BackseatDriverError, backseat_driver_error_handler)  # type: ignore
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    app.include_router(describe_router)
    app.include_router(jobs_router)
    return app


# `fastapi dev|run backseat_driver/api/app.py` looks for this module-level `app`.
app = create_app(get_settings())
