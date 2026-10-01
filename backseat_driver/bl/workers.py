"""Handlers for the two queue workers.

Plain classes over abstract ports, like `ScenePipeline`, so they are unit-testable with
fakes. They know nothing about Celery: `backseat_driver.tasks` wraps `handle` in a task. A
handler returns only once its work is durably recorded, which is what lets the task be
acked afterwards (at-least-once delivery), and every step is safe to run twice.
"""

from loguru import logger

from backseat_driver.bl.captioner import Captioner
from backseat_driver.bl.job_queue import JobQueue
from backseat_driver.bl.job_store import JobStore
from backseat_driver.bl.pipeline import describe_keyframe
from backseat_driver.bl.scene_loader import SceneLoader
from backseat_driver.models import CaptionTask, IngestTask


class IngestWorker:
    """Reads the dataset once per job and fans it out into one caption task per scene."""

    def __init__(self, loader: SceneLoader, queue: JobQueue, store: JobStore) -> None:
        self._loader = loader
        self._queue = queue
        self._store = store

    def handle(self, task: IngestTask) -> None:
        with logger.contextualize(job_id=str(task.job_id), transaction_id=task.transaction_id):
            keyframes = self._loader.load_keyframes()
            if task.max_scenes is not None:
                keyframes = keyframes[: task.max_scenes]

            # Recorded before fanning out, so a job can't look complete while tasks are still being published.
            self._store.set_expected_scenes(task.job_id, len(keyframes))
            for keyframe in keyframes:
                self._queue.enqueue_caption(
                    CaptionTask(job_id=task.job_id, transaction_id=task.transaction_id, keyframe=keyframe)
                )
            logger.bind(scenes=len(keyframes)).info("ingest fanned out")


class CaptionWorker:
    """Captions one scene's keyframe and records the result."""

    def __init__(self, captioner: Captioner, store: JobStore) -> None:
        self._captioner = captioner
        self._store = store

    def handle(self, task: CaptionTask) -> None:
        with logger.contextualize(job_id=str(task.job_id), transaction_id=task.transaction_id):
            description = describe_keyframe(task.keyframe, self._captioner)
            self._store.record_description(task.job_id, description)
            logger.bind(scene=task.keyframe.scene_name).info("scene described")
