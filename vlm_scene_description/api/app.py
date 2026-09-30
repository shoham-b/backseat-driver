from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from vlm_scene_description.api.errors import APIError
from vlm_scene_description.api.exception_handlers import (
    api_error_handler,
    domain_error_handler,
    unhandled_exception_handler,
)
from vlm_scene_description.api.middleware import RequestIDMiddleware
from vlm_scene_description.api.routers.describe import router as describe_router
from vlm_scene_description.api.routers.health import router as health_router
from vlm_scene_description.bl.captioner import BlipCaptioner
from vlm_scene_description.bl.errors import DomainError
from vlm_scene_description.config import get_settings
from vlm_scene_description.logger import LogFormat, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(LogFormat(settings.log_format), service="api")

    app.state.settings = settings
    app.state.captioner = BlipCaptioner(model_name=settings.vlm_model_name)

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
