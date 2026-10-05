"""Asynchronous batch jobs — describe a whole nuScenes dataset through the queue workers.

`POST /jobs` only records the job and enqueues an ingest task, then returns 202;
the ingest and caption workers do the actual work. Clients poll `GET /jobs/{id}`
until its state is `completed` (or `failed`, with the reason in `error`), then fetch the results.
"""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backseat_driver.api.dependencies import get_job_queue, get_job_store, get_transaction_id
from backseat_driver.api.errors import NOT_FOUND_RESPONSE
from backseat_driver.errors import IdempotencyKeyInUseError
from backseat_driver.models import DeadLetter, IngestTask, Job, JobDeadLetter, JobState, SceneDescription
from backseat_driver.transport.job_failure import describe_failure
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.write.job_store.job_store import JobStore

router = APIRouter(tags=["jobs"])


class CreateJobRequest(BaseModel):
    max_scenes: int | None = Field(default=None, gt=0, description="Only process the first N scenes")


@router.post("/jobs", status_code=HTTPStatus.ACCEPTED)
async def create_job(
    transaction_id: Annotated[str, Depends(get_transaction_id)],
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    store: Annotated[JobStore, Depends(get_job_store)],
    response: Response,
    body: CreateJobRequest | None = None,
    idempotency_key: Annotated[
        str | None,
        Header(
            pattern=r"^[A-Za-z0-9._-]+$",
            max_length=128,
            description="Retrying with the same key returns the job it created (200) instead of starting another.",
        ),
    ] = None,
) -> Job:
    """Start a job that describes every scene in the dataset."""
    max_scenes = body.max_scenes if body else None
    job_id = uuid4()

    # The store and queue clients are blocking, so keep them off the event loop like /describe does.
    if idempotency_key is not None:
        existing = await run_in_threadpool(store.find_job_by_idempotency_key, idempotency_key)
        if existing is not None:
            response.status_code = HTTPStatus.OK
            return existing
    try:
        await run_in_threadpool(store.create_job, job_id, max_scenes, transaction_id, idempotency_key)
    except IdempotencyKeyInUseError as exc:
        # A concurrent retry can pass the lookup above before the first request has created its job; the store's
        # unique key lets only one of them in, and this one answers with the job that won.
        existing = await run_in_threadpool(store.find_job_by_idempotency_key, exc.key)
        if existing is None:
            raise
        response.status_code = HTTPStatus.OK
        return existing
    task = IngestTask(job_id=job_id, transaction_id=transaction_id, max_scenes=max_scenes)
    try:
        await run_in_threadpool(queue.enqueue_ingest, task)
    except Exception as exc:
        # Otherwise the row would sit `pending` forever, waiting for an ingest task that was never queued.
        await run_in_threadpool(store.fail_job, job_id, describe_failure("enqueue", exc))
        raise
    return await run_in_threadpool(store.get_job, job_id)


@router.get("/jobs")
async def list_jobs(
    store: Annotated[JobStore, Depends(get_job_store)],
    state: JobState | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Job]:
    """Jobs, newest first, optionally only those in one `state`."""
    # Like create_job: the store is a blocking SQL client, so the listing stays off the event loop.
    return await run_in_threadpool(store.list_jobs, state, limit)


@router.get("/jobs/{job_id}", responses=NOT_FOUND_RESPONSE)
async def get_job(job_id: UUID, store: Annotated[JobStore, Depends(get_job_store)]) -> Job:
    """Progress of a job: `pending` until ingest counts the scenes, then `running`, then `completed`."""
    return await run_in_threadpool(store.get_job, job_id)


@router.get("/dead-letters")
async def list_recent_dead_letters(
    store: Annotated[JobStore, Depends(get_job_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[JobDeadLetter]:
    """The most recent tasks that ran out of retries across all jobs, newest first, each naming its job."""
    return await run_in_threadpool(store.list_recent_dead_letters, limit)


@router.get("/jobs/{job_id}/dead-letters", responses=NOT_FOUND_RESPONSE)
async def list_dead_letters(job_id: UUID, store: Annotated[JobStore, Depends(get_job_store)]) -> list[DeadLetter]:
    """The tasks of a job that ran out of retries, oldest first, each with its payload and the full error."""
    return await run_in_threadpool(store.list_dead_letters, job_id)


@router.get("/jobs/{job_id}/descriptions", responses=NOT_FOUND_RESPONSE)
async def list_descriptions(job_id: UUID, store: Annotated[JobStore, Depends(get_job_store)]) -> list[SceneDescription]:
    """Descriptions produced so far for a job (all of them once the job is `completed`)."""
    return await run_in_threadpool(store.list_descriptions, job_id)
