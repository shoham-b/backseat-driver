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
from backseat_driver.api.routers.images import router as images_router
from backseat_driver.api.routers.jobs import router as jobs_router
from backseat_driver.api.state import AppState
from backseat_driver.config import Settings, get_settings
from backseat_driver.errors import BackseatDriverError
from backseat_driver.logger import LogFormat, setup_logging
from backseat_driver.process.factory import build_captioner
from backseat_driver.stacks import build_image_store, build_job_backend


def create_app(settings: Settings) -> FastAPI:
    """Build the service for `settings`; tests build their own with `dependency_overrides` instead of patching."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        setup_logging(LogFormat(settings.log_format), service="api")

        captioner = build_captioner(settings)
        # The bucket in distributed mode, the local dataroot otherwise; a distributed API without a bucket fails here.
        image_store = build_image_store(settings)
        # In distributed mode neither client connects until first use, so startup never blocks on the broker
        # or database; /ready reports whether they are reachable.
        job_queue, job_store = build_job_backend(settings, captioner, image_store)
        app.state.services = AppState(settings, captioner, image_store, job_queue, job_store)

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
    app.include_router(images_router)
    return app


# `fastapi dev|run backseat_driver/api/app.py` looks for this module-level `app`.
app = create_app(get_settings())
