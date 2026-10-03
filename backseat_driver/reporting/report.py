"""Builds the model-vs-scene comparison behind the HTML report.

Pure data shaping: takes the `SceneDescription`s from one or more pipeline runs (one run per
model) and groups them by scene, scoring each against the nuScenes reference label.
"""

import re
from statistics import fmean

from pydantic import BaseModel

from backseat_driver.models import SceneDescription
from backseat_driver.reporting import metrics

_TOKEN_OR_GAP = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


class Segment(BaseModel):
    """A run of description text; `matched` words also appear in the reference label."""

    text: str
    matched: bool


class ModelEntry(BaseModel):
    model_name: str
    description: str
    segments: list[Segment]
    score: metrics.Score | None  # None when the scene has no reference label


class SceneRow(BaseModel):
    """One scene seen through one camera, with every model's description of it."""

    scene_token: str
    scene_name: str
    camera_channel: str
    image_path: str
    reference: str | None
    entries: list[ModelEntry]


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
    models: list[ModelSummary]
    cameras: list[str]


def build_report(descriptions: list[SceneDescription]) -> Report:
    """Group `descriptions` by scene and camera and score each against its reference.

    Raises ValueError when one model described the same scene through the same camera twice (two runs mixed up).
    """
    by_view: dict[tuple[str, str], list[SceneDescription]] = {}
    for d in descriptions:
        by_view.setdefault((d.scene_token, d.camera_channel), []).append(d)

    rows = [_scene_row(group) for group in by_view.values()]
    rows.sort(key=lambda r: (r.scene_name, r.camera_channel))
    model_names = sorted({d.model_name for d in descriptions})
    cameras = sorted({d.camera_channel for d in descriptions})
    return Report(scenes=rows, models=[_summarise(name, rows) for name in model_names], cameras=cameras)


def _scene_row(group: list[SceneDescription]) -> SceneRow:
    first = group[0]
    names = [d.model_name for d in group]
    if len(set(names)) != len(names):
        raise ValueError(
            f"scene {first.scene_name!r} ({first.camera_channel}) was described more than once "
            f"by the same model: {names}"
        )
    reference = next((d.reference_description for d in group if d.reference_description), None)
    entries = sorted((_entry(d, reference) for d in group), key=lambda e: e.model_name)
    return SceneRow(
        scene_token=first.scene_token,
        scene_name=first.scene_name,
        camera_channel=first.camera_channel,
        image_path=first.image_path,
        reference=reference,
        entries=entries,
    )


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
        score=metrics.score(d.description, reference) if reference else None,
    )


def _summarise(model_name: str, rows: list[SceneRow]) -> ModelSummary:
    entries = [e for row in rows for e in row.entries if e.model_name == model_name]
    scores = [e.score for e in entries if e.score is not None]
    return ModelSummary(
        model_name=model_name,
        scenes=len(entries),
        scored_scenes=len(scores),
        precision=fmean(s.precision for s in scores) if scores else None,
        recall=fmean(s.recall for s in scores) if scores else None,
        f1=fmean(s.f1 for s in scores) if scores else None,
        mean_words=fmean(len(e.description.split()) for e in entries),
    )
