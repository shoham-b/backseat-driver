from dataclasses import dataclass

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.config import Settings
from backseat_driver.datasets.image_store import ImageStore
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore


@dataclass(frozen=True)
class AppState:
    """What the lifespan builds once per process; the dependencies in `dependencies.py` hand it out piece by piece."""

    settings: Settings
    captioner: Captioner
    image_store: ImageStore
    job_queue: JobQueue
    job_store: JobStore
