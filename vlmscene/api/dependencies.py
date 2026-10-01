from fastapi import Request

from vlmscene.bl.captioner import Captioner
from vlmscene.bl.job_queue import JobQueue
from vlmscene.bl.job_store import JobStore


def get_captioner(request: Request) -> Captioner:
    return request.app.state.captioner  # type: ignore[no-any-return]


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue  # type: ignore[no-any-return]


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store  # type: ignore[no-any-return]
