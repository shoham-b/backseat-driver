import tempfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore


def get_captioner(request: Request) -> Captioner:
    return request.app.state.captioner  # type: ignore[no-any-return]


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue  # type: ignore[no-any-return]


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store  # type: ignore[no-any-return]


def get_upload_dir() -> Iterator[Path]:
    """A scratch directory for one request's upload, removed once the request is done."""
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)
