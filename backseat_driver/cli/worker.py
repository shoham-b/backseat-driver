"""Queue workers for the distributed mode — long-running Celery workers, one per queue.

Usage::

    backseat-driver worker ingest
    backseat-driver worker ingest --once   # one task, then exit (a Job per queued task)
    backseat-driver worker caption
"""

from typing import Annotated

import typer

from backseat_driver.cli import worker_app
from backseat_driver.config import get_settings
from backseat_driver.logger import LogFormat, setup_logging

# Gossip, mingle and heartbeat are worker-to-worker chatter that needs the remote-control queues (see make_celery_app).
_NO_CLUSTER = ["--without-gossip", "--without-mingle", "--without-heartbeat"]


@worker_app.command()
def ingest(
    once: Annotated[
        bool,
        typer.Option("--once", help="Handle one task, then exit, for a run-to-completion Job started per queued task"),
    ] = False,
) -> None:
    """Consume ingest tasks: load the dataset metadata and fan out one caption task per scene."""
    from backseat_driver.tasks import celery_app
    from backseat_driver.transport.celery_job_queue import INGEST_QUEUE
    from backseat_driver.transport.consume_one import consume_one

    setup_logging(LogFormat(get_settings().log_format), service="ingest-worker")
    if once:
        consume_one(celery_app, INGEST_QUEUE)
        return
    celery_app.worker_main(["worker", "-Q", INGEST_QUEUE, "-n", "ingest@%h", "--pool=solo", *_NO_CLUSTER])


@worker_app.command()
def caption() -> None:
    """Consume caption tasks: run each scene's keyframe through the VLM and record the result."""
    from backseat_driver.tasks import celery_app, workers
    from backseat_driver.transport.celery_job_queue import CAPTION_QUEUE

    setup_logging(LogFormat(get_settings().log_format), service="caption-worker")
    # Load the model before consuming, not on the first message: a model that can't load should
    # fail the worker at startup, not leave it pulling messages it would fail every time.
    _ = workers.caption_worker
    worker = celery_app.Worker(
        queues=[CAPTION_QUEUE],
        hostname="caption@%h",
        pool_cls="solo",
        without_gossip=True,
        without_mingle=True,
        without_heartbeat=True,
    )
    worker.start()
    raise typer.Exit(worker.exitcode)
