"""Message handlers for the two queue workers.

Plain classes over Protocols, like `ScenePipeline`, so they are unit-testable with
fakes. `handle` is the `MessageHandler` a queue consumer calls per message; it
returns only once the work is durably recorded, which is what lets the queue ack
after the fact (at-least-once delivery).
"""

from collections.abc import Mapping
from uuid import UUID

from loguru import logger

from vlmscene.bl.captioner import Captioner
from vlmscene.bl.job_queue import CAPTION_QUEUE, REQUEST_ID_HEADER, JobQueue
from vlmscene.bl.job_store import JobStore
from vlmscene.bl.nuscenes_loader import SceneLoader
from vlmscene.bl.pipeline import describe_keyframe
from vlmscene.models import CaptionTask, IngestTask


def _log_context(job_id: UUID, headers: Mapping[str, str]) -> dict[str, str]:
    context = {"job_id": str(job_id)}
    if REQUEST_ID_HEADER in headers:
        context["request_id"] = headers[REQUEST_ID_HEADER]
    return context


class IngestWorker:
    """Reads the dataset once per job and fans it out into one caption task per scene."""

    def __init__(self, loader: SceneLoader, queue: JobQueue, store: JobStore) -> None:
        self._loader = loader
        self._queue = queue
        self._store = store

    def handle(self, body: bytes, headers: Mapping[str, str]) -> None:
        task = IngestTask.model_validate_json(body)
        with logger.contextualize(**_log_context(task.job_id, headers)):
            keyframes = self._loader.load_keyframes()
            if task.max_scenes is not None:
                keyframes = keyframes[: task.max_scenes]

            # Recorded before fanning out, so a job can't look complete while tasks are still being published.
            self._store.set_expected_scenes(task.job_id, len(keyframes))
            for keyframe in keyframes:
                caption_task = CaptionTask(job_id=task.job_id, keyframe=keyframe)
                self._queue.publish(CAPTION_QUEUE, caption_task.model_dump_json().encode(), headers)
            logger.bind(scenes=len(keyframes)).info("ingest fanned out")


class CaptionWorker:
    """Captions one scene's keyframe and records the result."""

    def __init__(self, captioner: Captioner, store: JobStore) -> None:
        self._captioner = captioner
        self._store = store

    def handle(self, body: bytes, headers: Mapping[str, str]) -> None:
        task = CaptionTask.model_validate_json(body)
        with logger.contextualize(**_log_context(task.job_id, headers)):
            description = describe_keyframe(task.keyframe, self._captioner)
            self._store.record_description(task.job_id, description)
            logger.bind(scene=task.keyframe.scene_name).info("scene described")
