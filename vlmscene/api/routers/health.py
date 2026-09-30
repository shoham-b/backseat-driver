from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from vlmscene.api.dependencies import get_captioner, get_job_queue, get_job_store
from vlmscene.api.errors import APIError
from vlmscene.bl.captioner import Captioner
from vlmscene.bl.job_queue import JobQueue
from vlmscene.bl.job_store import JobStore

router = APIRouter(tags=["observability"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    captioner: Annotated[Captioner, Depends(get_captioner)],
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, str]:
    """Readiness probe — returns 200 only when all dependencies are reachable."""
    if not captioner.healthcheck():
        raise APIError("VLM captioner unavailable", HTTPStatus.SERVICE_UNAVAILABLE)
    # Both probes do blocking network I/O.
    if not await run_in_threadpool(queue.healthcheck):
        raise APIError("message queue unavailable", HTTPStatus.SERVICE_UNAVAILABLE)
    if not await run_in_threadpool(store.healthcheck):
        raise APIError("job store unavailable", HTTPStatus.SERVICE_UNAVAILABLE)

    return {"status": "ok"}
