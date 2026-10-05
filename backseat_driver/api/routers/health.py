import asyncio
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends

from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from backseat_driver.api.errors import UNAVAILABLE_RESPONSE, APIError
from backseat_driver.process.captioner import Captioner
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.transport.job_store.job_store import JobStore

router = APIRouter(tags=["observability"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/ready", responses=UNAVAILABLE_RESPONSE)
def readiness(
    captioner: Annotated[Captioner, Depends(get_captioner)],
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, str]:
    """Readiness probe — returns 200 only when all dependencies are reachable.

    A plain `def` (run on a worker thread): the probes do blocking network I/O.
    """
    if not asyncio.run(captioner.healthcheck()):
        raise APIError("VLM captioner unavailable", HTTPStatus.SERVICE_UNAVAILABLE)
    if not queue.healthcheck():
        raise APIError("message queue unavailable", HTTPStatus.SERVICE_UNAVAILABLE)
    if not store.healthcheck():
        raise APIError("job store unavailable", HTTPStatus.SERVICE_UNAVAILABLE)

    return {"status": "ok"}
