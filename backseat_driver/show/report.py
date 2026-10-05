"""Builds the model-vs-scene comparison behind the HTML report.

Pure data shaping: takes the `SceneDescription`s from one or more pipeline runs (one run per
model) and groups them by scene, scoring each against the nuScenes reference label.

The label describes the whole scene, so a model is scored once per scene on all of its camera
captions combined, never camera by camera (a back camera cannot mention the van ahead).
"""

import re
from collections import defaultdict
from statistics import fmean

from pydantic import BaseModel

from backseat_driver.models import SceneDescription
from backseat_driver.show import metrics

_TOKEN_OR_GAP = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


class Segment(BaseModel):
    """A run of description text; `matched` words also appear in the reference label."""

    text: str
    matched: bool


class ModelEntry(BaseModel):
    model_name: str
    description: str
    segments: list[Segment]


class SceneRow(BaseModel):
    """One scene seen through one camera, with every model's description of it."""

    scene_token: str
    scene_name: str
    camera_channel: str
    image_path: str
    reference: str | None
    entries: list[ModelEntry]


class SceneScore(BaseModel):
    """One model scored on one scene, over all of its camera captions together."""

    scene_token: str
    model_name: str
    cameras: int
    score: metrics.Score | None  # None when the scene has no reference label


class ModelSummary(BaseModel):
    """Mean metrics over the scenes this model was scored on."""

    model_name: str
    scenes: int
    scored_scenes: int
    precision: float | None
    recall: float | None
    f1: float | None
    mean_words: float


class Report(BaseModel):
    scenes: list[SceneRow]
    scene_scores: list[SceneScore]
    models: list[ModelSummary]
    cameras: list[str]


def build_report(descriptions: list[SceneDescription]) -> Report:
    """Group `descriptions` by scene and camera and score each against its reference.

    Raises ValueError when one model described the same scene through the same camera twice (two runs mixed up).
    """
    by_view: defaultdict[tuple[str, str], list[SceneDescription]] = defaultdict(list)
    for d in descriptions:
        by_view[d.scene_token, d.camera_channel].append(d)

    rows = [_scene_row(group) for group in by_view.values()]
    rows.sort(key=lambda r: (r.scene_name, r.camera_channel))
    model_names = sorted({d.model_name for d in descriptions})
    cameras = sorted({d.camera_channel for d in descriptions})
    scene_scores = _scene_scores(descriptions)
    return Report(
        scenes=rows,
        scene_scores=scene_scores,
        models=[_summarise(name, rows, scene_scores) for name in model_names],
        cameras=cameras,
    )


def _scene_row(group: list[SceneDescription]) -> SceneRow:
    first = group[0]
    names = [d.model_name for d in group]
    if len(set(names)) != len(names):
        raise ValueError(
            f"scene {first.scene_name!r} ({first.camera_channel}) was described more than once "
            f"by the same model: {names}"
        )
    reference = _reference_of(group)
    entries = sorted((_entry(d, reference) for d in group), key=lambda e: e.model_name)
    return SceneRow(
        scene_token=first.scene_token,
        scene_name=first.scene_name,
        camera_channel=first.camera_channel,
        image_path=first.image_path,
        reference=reference,
        entries=entries,
    )


def _reference_of(group: list[SceneDescription]) -> str | None:
    return next((d.reference_description for d in group if d.reference_description), None)


def _scene_scores(descriptions: list[SceneDescription]) -> list[SceneScore]:
    by_scene_model: defaultdict[tuple[str, str], list[SceneDescription]] = defaultdict(list)
    for d in descriptions:
        by_scene_model[d.scene_token, d.model_name].append(d)

    scores = []
    for (scene_token, model_name), group in sorted(by_scene_model.items()):
        reference = _reference_of(group)
        combined = " ".join(d.description for d in sorted(group, key=lambda d: d.camera_channel))
        scores.append(
            SceneScore(
                scene_token=scene_token,
                model_name=model_name,
                cameras=len(group),
                score=metrics.score(combined, reference) if reference else None,
            )
        )
    return scores


def _entry(d: SceneDescription, reference: str | None) -> ModelEntry:
    ref_words = metrics.content_words(reference) if reference else set()
    segments = [
        Segment(text=part, matched=(w := metrics.normalize_word(part)) is not None and w in ref_words)
        for part in _TOKEN_OR_GAP.findall(d.description)
    ]
    return ModelEntry(
        model_name=d.model_name,
        description=d.description,
        segments=segments,
    )


def _summarise(model_name: str, rows: list[SceneRow], scene_scores: list[SceneScore]) -> ModelSummary:
    entries = [e for row in rows for e in row.entries if e.model_name == model_name]
    own = [s for s in scene_scores if s.model_name == model_name]
    scores = [s.score for s in own if s.score is not None]
    return ModelSummary(
        model_name=model_name,
        scenes=len(own),
        scored_scenes=len(scores),
        precision=fmean(s.precision for s in scores) if scores else None,
        recall=fmean(s.recall for s in scores) if scores else None,
        f1=fmean(s.f1 for s in scores) if scores else None,
        mean_words=fmean(len(e.description.split()) for e in entries),
    )
