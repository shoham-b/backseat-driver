"""Handler for the ingest worker: the read step as a producer.

A plain class over abstract ports, like `ScenePipeline`, so it is unit-testable with fakes. It
knows nothing about Celery: `backseat_driver.tasks` wraps `handle` in a task. `handle` returns only
once its work is durably recorded, which is what lets the task be acked afterwards (at-least-once
delivery), and every step is safe to run twice.
"""

from loguru import logger

from backseat_driver.models import CaptionTask, IngestTask
from backseat_driver.pipeline import first_scenes
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.read.images.image_store import ImageStore
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.write.job_store.job_store import JobStore


class IngestWorker:
    """Reads the dataset once per job and fans out one caption task per keyframe (a scene and a camera), each pointing
    at its image."""

    def __init__(self, loader: SceneLoader, queue: JobQueue, store: JobStore, images: ImageStore) -> None:
        self._loader = loader
        self._queue = queue
        self._store = store
        self._images = images

    def handle(self, task: IngestTask) -> None:
        with logger.contextualize(job_id=str(task.job_id), transaction_id=task.transaction_id):
            keyframes = first_scenes(self._loader.load_keyframes(), task.max_scenes)

            # One description is recorded per keyframe, so that is what the job expects. Recorded before fanning out,
            # so a job can't look complete while tasks are still being published.
            self._store.set_expected_scenes(task.job_id, len(keyframes))
            for keyframe in keyframes:
                self._queue.enqueue_caption(
                    CaptionTask(
                        job_id=task.job_id,
                        transaction_id=task.transaction_id,
                        keyframe=keyframe,
                        image_uri=self._images.uri_for(keyframe.image_path),
                    )
                )
            logger.info("ingest fanned out {} keyframes to caption workers", len(keyframes))
