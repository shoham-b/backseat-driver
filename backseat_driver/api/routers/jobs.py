"""Asynchronous batch jobs — describe a whole nuScenes dataset through the queue workers.

`POST /jobs` only records the job and enqueues an ingest task, then returns 202;
the ingest and caption workers do the actual work. Clients poll `GET /jobs/{id}`
until its state is `completed`, then fetch the results.
"""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backseat_driver.api.dependencies import get_job_queue, get_job_store
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore
from backseat_driver.models import IngestTask, Job, SceneDescription

router = APIRouter(tags=["jobs"])


class CreateJobRequest(BaseModel):
    max_scenes: int | None = Field(default=None, gt=0, description="Only process the first N scenes")


@router.post("/jobs", status_code=HTTPStatus.ACCEPTED)
async def create_job(
    request: Request,
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    store: Annotated[JobStore, Depends(get_job_store)],
    body: CreateJobRequest | None = None,
) -> Job:
    """Start a job that describes every scene in the dataset."""
    max_scenes = body.max_scenes if body else None
    job_id = uuid4()
    transaction_id: str = request.state.request_id

    # The store and queue clients are blocking, so keep them off the event loop like /describe does.
    await run_in_threadpool(store.create_job, job_id, max_scenes, transaction_id)
    task = IngestTask(job_id=job_id, transaction_id=transaction_id, max_scenes=max_scenes)
    await run_in_threadpool(queue.enqueue_ingest, task)
    return await run_in_threadpool(store.get_job, job_id)


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, store: Annotated[JobStore, Depends(get_job_store)]) -> Job:
    """Progress of a job: `pending` until ingest counts the scenes, then `running`, then `completed`."""
    return await run_in_threadpool(store.get_job, job_id)


@router.get("/jobs/{job_id}/descriptions")
async def list_descriptions(job_id: UUID, store: Annotated[JobStore, Depends(get_job_store)]) -> list[SceneDescription]:
    """Descriptions produced so far for a job (all of them once the job is `completed`)."""
    return await run_in_threadpool(store.list_descriptions, job_id)
