from dataclasses import dataclass

from backseat_driver.config import Settings
from backseat_driver.process.captioner import Captioner
from backseat_driver.read.images.image_store import ImageStore
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.write.job_store.job_store import JobStore


@dataclass(frozen=True)
class AppState:
    """What the lifespan builds once per process; the dependencies in `dependencies.py` hand it out piece by piece."""

    settings: Settings
    captioner: Captioner
    image_store: ImageStore
    job_queue: JobQueue
    job_store: JobStore
