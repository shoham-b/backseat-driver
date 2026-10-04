"""Handler for the caption worker: the process and write steps, once per task.

A plain class over abstract ports, so it is unit-testable with fakes. It knows nothing about
Celery: `backseat_driver.tasks` wraps `handle` in a task. `handle` returns only once the
description is recorded, which is what lets the task be acked afterwards (at-least-once
delivery), and recording it twice is safe.
"""

from loguru import logger

from backseat_driver.models import CaptionTask
from backseat_driver.pipeline import describe_keyframe
from backseat_driver.process.captioner import Captioner
from backseat_driver.read.images.image_store import ImageStore
from backseat_driver.write.job_store.job_store import JobStore


class CaptionWorker:
    """Captions one scene's keyframe from a local copy of its image and records the result."""

    def __init__(self, captioner: Captioner, store: JobStore, images: ImageStore) -> None:
        self._captioner = captioner
        self._store = store
        self._images = images

    def handle(self, task: CaptionTask) -> None:
        with logger.contextualize(job_id=str(task.job_id), transaction_id=task.transaction_id):
            with self._images.local_copy(task.image_uri) as local_path:
                description = describe_keyframe(task.keyframe, self._captioner, str(local_path))
            self._store.record_description(task.job_id, description)
            logger.debug("described {} ({})", task.keyframe.scene_name, task.keyframe.camera_channel)
