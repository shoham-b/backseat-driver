import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from backseat_driver.models import SceneKeyframe
from backseat_driver.pipeline import ScenePipeline, describe_keyframes
from tests.fakes import FakeCaptioner, FakeImageStore, FakeSceneLoader


def _keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n}",
        camera_channel="CAM_FRONT",
        image_path=f"samples/CAM_FRONT/scene-{n}.jpg",
    )


async def test_run_describes_every_scene() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=captioner, images=FakeImageStore())

    descriptions = await pipeline.run()

    assert len(descriptions) == 3
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2", "scene-3"]
    assert all(d.model_name == "fake-model" for d in descriptions)
    assert captioner.seen_paths == [str(Path("/fetched") / f"scene-{n}.jpg") for n in (1, 2, 3)]


async def test_run_respects_max_scenes() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore())

    descriptions = await pipeline.run(max_scenes=2)

    assert len(descriptions) == 2
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2"]


@pytest.mark.parametrize("max_scenes", [0, -1])
async def test_run_rejects_a_max_scenes_below_one_instead_of_slicing(max_scenes: int) -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=captioner, images=FakeImageStore())

    with pytest.raises(ValueError, match="max_scenes must be at least 1"):
        await pipeline.run(max_scenes=max_scenes)

    assert captioner.seen_paths == []


async def test_run_on_empty_dataset_returns_empty_list() -> None:
    pipeline = ScenePipeline(loader=FakeSceneLoader([]), captioner=FakeCaptioner(), images=FakeImageStore())

    descriptions = await pipeline.run()

    assert descriptions == []


async def test_description_carries_keyframe_fields_through() -> None:
    keyframe = _keyframe(1)
    pipeline = ScenePipeline(loader=FakeSceneLoader([keyframe]), captioner=FakeCaptioner(), images=FakeImageStore())

    [description] = await pipeline.run()

    assert description.scene_token == keyframe.scene_token
    assert description.camera_channel == keyframe.camera_channel
    assert description.image_path == keyframe.image_path
    assert description.description == f"a caption for {Path('/fetched') / 'scene-1.jpg'}"


async def test_max_scenes_counts_scenes_not_cameras() -> None:
    keyframes = [
        _keyframe(1).model_copy(update={"camera_channel": channel}) for channel in ("CAM_FRONT", "CAM_BACK")
    ] + [_keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore())

    descriptions = await pipeline.run(max_scenes=2)

    assert [(d.scene_name, d.camera_channel) for d in descriptions] == [
        ("scene-1", "CAM_FRONT"),
        ("scene-1", "CAM_BACK"),
        ("scene-2", "CAM_FRONT"),
    ]


async def test_run_reports_progress_before_each_keyframe() -> None:
    keyframes = [_keyframe(1), _keyframe(2)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore())
    seen: list[tuple[int, int, str]] = []

    await pipeline.run(on_progress=lambda index, total, kf: seen.append((index, total, kf.scene_name)))

    assert seen == [(1, 2, "scene-1"), (2, 2, "scene-2")]


async def test_run_captions_a_local_copy_of_each_image_and_releases_it() -> None:
    keyframes = [_keyframe(1), _keyframe(2)]
    images = FakeImageStore()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=images)

    await pipeline.run()

    expected = [f"fake://samples/CAM_FRONT/scene-{n}.jpg" for n in (1, 2)]
    assert images.opened == expected
    assert images.released == expected


class _FailingCaptioner(FakeCaptioner):
    async def caption(self, image_path: str) -> str:
        raise RuntimeError("model exploded")


async def test_run_propagates_a_captioning_failure_and_still_releases_the_local_copy() -> None:
    images = FakeImageStore()
    pipeline = ScenePipeline(loader=FakeSceneLoader([_keyframe(1)]), captioner=_FailingCaptioner(), images=images)

    with pytest.raises(RuntimeError, match="model exploded"):
        await pipeline.run()

    assert images.released == images.opened == ["fake://samples/CAM_FRONT/scene-1.jpg"]


async def test_run_captions_in_batches_of_batch_size() -> None:
    keyframes = [_keyframe(n) for n in range(1, 6)]
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(
        loader=FakeSceneLoader(keyframes), captioner=captioner, images=FakeImageStore(), batch_size=2
    )

    descriptions = await pipeline.run()

    assert [len(batch) for batch in captioner.batches] == [2, 2, 1]
    assert [d.scene_name for d in descriptions] == [f"scene-{n}" for n in range(1, 6)]


async def test_run_reports_progress_once_per_batch_with_its_first_keyframe() -> None:
    keyframes = [_keyframe(n) for n in range(1, 6)]
    pipeline = ScenePipeline(
        loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore(), batch_size=2
    )
    seen: list[tuple[int, int, str]] = []

    await pipeline.run(on_progress=lambda index, total, kf: seen.append((index, total, kf.scene_name)))

    assert seen == [(1, 5, "scene-1"), (3, 5, "scene-3"), (5, 5, "scene-5")]


async def test_run_holds_every_local_copy_of_a_batch_until_the_batch_is_captioned() -> None:
    images = FakeImageStore()
    pipeline = ScenePipeline(
        loader=FakeSceneLoader([_keyframe(1), _keyframe(2)]),
        captioner=FakeCaptioner(),
        images=images,
        batch_size=2,
    )

    await pipeline.run()

    assert images.opened == images.released[::-1]


async def test_run_loads_the_captioner() -> None:
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader([_keyframe(1)]), captioner=captioner, images=FakeImageStore())

    await pipeline.run()

    assert captioner.loads == 1


class _UnloadableCaptioner(FakeCaptioner):
    async def load(self) -> None:
        raise RuntimeError("no weights")


async def test_run_fails_when_the_captioner_cannot_load_before_captioning_anything() -> None:
    captioner = _UnloadableCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader([_keyframe(1)]), captioner=captioner, images=FakeImageStore())

    with pytest.raises(RuntimeError, match="no weights"):
        await pipeline.run()

    assert captioner.seen_paths == []


@pytest.mark.parametrize("batch_size", [0, -1])
async def test_a_batch_size_below_one_is_rejected(batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch_size must be at least 1"):
        ScenePipeline(
            loader=FakeSceneLoader([]), captioner=FakeCaptioner(), images=FakeImageStore(), batch_size=batch_size
        )


async def test_describe_keyframes_rejects_a_path_count_that_differs_from_the_keyframe_count() -> None:
    with pytest.raises(ValueError, match="1 local paths for 2 keyframes"):
        await describe_keyframes([_keyframe(1), _keyframe(2)], FakeCaptioner(), ["a.jpg"])


class _RendezvousImageStore(FakeImageStore):
    """No copy is handed out until `parties` were asked for: fetched one at a time, the first would wait forever."""

    def __init__(self, parties: int, failing: str | None = None) -> None:
        super().__init__()
        self._parties = parties
        self._failing = failing
        self._asked = 0
        self._all_asked = asyncio.Event()

    @asynccontextmanager
    async def local_copy(self, uri: str) -> AsyncIterator[Path]:
        self._asked += 1
        if self._asked == self._parties:
            self._all_asked.set()
        await asyncio.wait_for(self._all_asked.wait(), timeout=5)
        if self._failing is not None and uri.endswith(self._failing):
            raise FileNotFoundError(uri)
        async with super().local_copy(uri) as path:
            yield path


async def test_run_fetches_the_local_copies_of_a_batch_together() -> None:
    images = _RendezvousImageStore(parties=3)
    pipeline = ScenePipeline(
        loader=FakeSceneLoader([_keyframe(n) for n in range(1, 4)]),
        captioner=FakeCaptioner(),
        images=images,
        batch_size=3,
    )

    descriptions = await pipeline.run()

    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2", "scene-3"]
    assert sorted(images.released) == sorted(images.opened)


async def test_run_raises_a_failed_fetch_as_itself_and_releases_the_copies_already_made() -> None:
    images = _RendezvousImageStore(parties=3, failing="scene-2.jpg")
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(
        loader=FakeSceneLoader([_keyframe(n) for n in range(1, 4)]),
        captioner=captioner,
        images=images,
        batch_size=3,
    )

    with pytest.raises(FileNotFoundError, match=r"scene-2\.jpg"):
        await pipeline.run()

    assert captioner.seen_paths == []
    assert sorted(images.released) == sorted(images.opened)
