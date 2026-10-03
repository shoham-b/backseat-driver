"""Queue workers for the distributed mode — long-running Celery workers, one per queue.

Usage::

    backseat-driver worker ingest
    backseat-driver worker caption
"""

import typer

from backseat_driver.cli import worker_app
from backseat_driver.cli.context import cli_context
from backseat_driver.jobs.celery_job_queue import CAPTION_QUEUE, INGEST_QUEUE
from backseat_driver.logger import LogFormat

# Gossip, mingle and heartbeat are worker-to-worker chatter that needs the remote-control queues (see make_celery_app).
_NO_CLUSTER = ["--without-gossip", "--without-mingle", "--without-heartbeat"]


@worker_app.command()
def ingest(ctx: typer.Context) -> None:
    """Consume ingest tasks: load the dataset and fan out one caption task per scene."""
    deps = cli_context(ctx)
    deps.configure_logging(LogFormat(deps.settings.log_format), "ingest-worker")
    deps.start_worker(["worker", "-Q", INGEST_QUEUE, "-n", "ingest@%h", "--pool=solo", *_NO_CLUSTER])


@worker_app.command()
def caption(ctx: typer.Context) -> None:
    """Consume caption tasks: run each scene's keyframe through the VLM and record the result."""
    deps = cli_context(ctx)
    deps.configure_logging(LogFormat(deps.settings.log_format), "caption-worker")
    # Load the model before consuming, not on the first message: a model that can't load should
    # fail the worker at startup, not leave it pulling messages it would fail every time.
    deps.load_caption_model()
    deps.start_worker(["worker", "-Q", CAPTION_QUEUE, "-n", "caption@%h", "--pool=solo", *_NO_CLUSTER])
