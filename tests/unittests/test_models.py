import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from backseat_driver.models import CaptionTask, IngestTask, Job, JobState, SceneDescription, SceneKeyframe

_text = st.text(min_size=1, max_size=40)
_keyframes = st.builds(SceneKeyframe, scene_token=_text, scene_name=_text, camera_channel=_text, image_path=_text)


def _keyframe() -> SceneKeyframe:
    return SceneKeyframe(scene_token="t", scene_name="n", camera_channel="CAM_FRONT", image_path="/p.jpg")


@given(keyframe=_keyframes, job_id=st.uuids(), transaction_id=_text)
def test_caption_task_survives_the_json_round_trip_the_queue_applies(
    keyframe: SceneKeyframe, job_id: UUID, transaction_id: str
) -> None:
    task = CaptionTask(job_id=job_id, transaction_id=transaction_id, keyframe=keyframe)

    wire = json.loads(json.dumps(task.model_dump(mode="json")))

    assert CaptionTask.model_validate(wire) == task


@given(job_id=st.uuids(), transaction_id=_text, max_scenes=st.none() | st.integers(min_value=1, max_value=10_000))
def test_ingest_task_survives_the_json_round_trip_the_queue_applies(
    job_id: UUID, transaction_id: str, max_scenes: int | None
) -> None:
    task = IngestTask(job_id=job_id, transaction_id=transaction_id, max_scenes=max_scenes)

    wire = json.loads(json.dumps(task.model_dump(mode="json")))

    assert IngestTask.model_validate(wire) == task


def test_ingest_task_max_scenes_defaults_to_everything() -> None:
    assert IngestTask(job_id=uuid4(), transaction_id="tx").max_scenes is None


def test_scene_description_timestamp_defaults_to_now_in_utc() -> None:
    before = datetime.now(UTC)

    description = SceneDescription(**_keyframe().model_dump(), description="d", model_name="m")

    assert before <= description.generated_at <= datetime.now(UTC)
    assert description.generated_at.tzinfo is not None


def test_scene_description_timestamps_are_independent_per_instance() -> None:
    fields = {**_keyframe().model_dump(), "description": "d", "model_name": "m"}

    first, second = SceneDescription(**fields), SceneDescription(**fields)

    assert first.generated_at <= second.generated_at


@pytest.mark.parametrize("missing", ["scene_token", "scene_name", "camera_channel", "image_path"])
def test_keyframe_requires_every_field(missing: str) -> None:
    fields = _keyframe().model_dump()
    del fields[missing]

    with pytest.raises(ValidationError, match=missing):
        SceneKeyframe(**fields)


@pytest.mark.parametrize("payload", [{}, {"job_id": "not-a-uuid", "transaction_id": "t"}, {"job_id": str(uuid4())}])
def test_ingest_task_rejects_malformed_payloads(payload: dict) -> None:
    with pytest.raises(ValidationError):
        IngestTask.model_validate(payload)


def test_caption_task_rejects_a_payload_without_a_keyframe() -> None:
    with pytest.raises(ValidationError, match="keyframe"):
        CaptionTask.model_validate({"job_id": str(uuid4()), "transaction_id": "t"})


def test_job_state_serialises_to_its_lowercase_value() -> None:
    job = Job(
        job_id=uuid4(),
        transaction_id="tx",
        state=JobState.RUNNING,
        max_scenes=None,
        expected_scenes=3,
        completed_scenes=1,
        created_at=datetime.now(UTC),
    )

    dumped = job.model_dump(mode="json")

    assert dumped["state"] == "running"
    assert dumped["max_scenes"] is None


def test_job_rejects_an_unknown_state() -> None:
    with pytest.raises(ValidationError):
        Job(
            job_id=uuid4(),
            transaction_id="tx",
            state="finished",
            max_scenes=None,
            expected_scenes=None,
            completed_scenes=0,
            created_at=datetime.now(UTC),
        )


def test_job_state_values_are_the_documented_api_contract() -> None:
    assert [s.value for s in JobState] == ["pending", "running", "completed"]
