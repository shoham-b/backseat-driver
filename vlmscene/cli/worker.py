"""Queue workers for the distributed mode — long-running Celery workers, one per queue.

Usage::

    vlm-scene-description worker ingest
    vlm-scene-description worker caption
"""

from vlmscene.cli import worker_app
from vlmscene.config import get_settings
from vlmscene.logger import LogFormat, setup_logging

# Gossip, mingle and heartbeat are worker-to-worker chatter that needs the remote-control queues (see make_celery_app).
_NO_CLUSTER = ["--without-gossip", "--without-mingle", "--without-heartbeat"]


@worker_app.command()
def ingest() -> None:
    """Consume ingest tasks: load the dataset and fan out one caption task per scene."""
    from vlmscene.bl.job_queue import INGEST_QUEUE
    from vlmscene.tasks import celery_app

    setup_logging(LogFormat(get_settings().log_format), service="ingest-worker")
    celery_app.worker_main(["worker", "-Q", INGEST_QUEUE, "-n", "ingest@%h", "--pool=solo", *_NO_CLUSTER])


@worker_app.command()
def caption() -> None:
    """Consume caption tasks: run each scene's keyframe through the VLM and record the result."""
    from vlmscene.bl.job_queue import CAPTION_QUEUE
    from vlmscene.tasks import caption_worker, celery_app

    setup_logging(LogFormat(get_settings().log_format), service="caption-worker")
    # Load the model before consuming, not on the first message: a model that can't load should
    # fail the worker at startup, not leave it pulling messages it would fail every time.
    caption_worker()
    celery_app.worker_main(["worker", "-Q", CAPTION_QUEUE, "-n", "caption@%h", "--pool=solo", *_NO_CLUSTER])
