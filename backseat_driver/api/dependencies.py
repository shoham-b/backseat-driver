import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from backseat_driver.api.state import AppState
from backseat_driver.captioning.captioner import Captioner
from backseat_driver.config import Settings
from backseat_driver.datasets.image_service import ImageService
from backseat_driver.datasets.image_store import ImageStore
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore


def get_app_state(request: Request) -> AppState:
    # AttributeError if the lifespan never ran: fail fast rather than serve with half-built collaborators.
    return request.app.state.services  # type: ignore[no-any-return]


def get_app_settings(state: Annotated[AppState, Depends(get_app_state)]) -> Settings:
    return state.settings


def get_captioner(state: Annotated[AppState, Depends(get_app_state)]) -> Captioner:
    return state.captioner


def get_image_store(state: Annotated[AppState, Depends(get_app_state)]) -> ImageStore:
    return state.image_store


def get_image_service(store: Annotated[ImageStore, Depends(get_image_store)]) -> ImageService:
    # Built per request from the store: the service is cheap, the store (its client) lives as long as the app.
    return ImageService(store)


def get_job_queue(state: Annotated[AppState, Depends(get_app_state)]) -> JobQueue:
    return state.job_queue


def get_job_store(state: Annotated[AppState, Depends(get_app_state)]) -> JobStore:
    return state.job_store


def get_request_id(request: Request) -> str:
    return request.state.request_id  # type: ignore[no-any-return]


def get_upload_dir() -> Iterator[Path]:
    """A scratch directory for one request's upload, removed once the request is done."""
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)
