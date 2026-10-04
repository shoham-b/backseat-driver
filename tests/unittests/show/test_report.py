import json

import pytest

from backseat_driver.models import SceneDescription
from backseat_driver.show.html_report_writer import render_html
from backseat_driver.show.report import build_report


def _desc(
    scene: int, model: str, text: str, reference: str | None = "parked truck", camera: str = "CAM_FRONT"
) -> SceneDescription:
    return SceneDescription(
        scene_token=f"token-{scene}",
        scene_name=f"scene-{scene:04d}",
        camera_channel=camera,
        image_path=f"/img/{scene}.jpg",
        description=text,
        model_name=model,
        reference_description=reference,
    )


def test_build_report_groups_models_under_each_scene() -> None:
    descriptions = [_desc(2, "a", "x"), _desc(1, "b", "parked truck"), _desc(1, "a", "a truck")]

    report = build_report(descriptions)

    assert [s.scene_name for s in report.scenes] == ["scene-0001", "scene-0002"]
    assert [e.model_name for e in report.scenes[0].entries] == ["a", "b"]


def test_build_report_summarises_mean_metrics_per_model() -> None:
    descriptions = [_desc(1, "a", "parked truck"), _desc(2, "a", "sunny beach")]

    report = build_report(descriptions)

    [summary] = report.models
    assert summary.scored_scenes == 2
    assert summary.f1 == pytest.approx(0.5)


def test_build_report_marks_words_found_in_the_reference() -> None:
    descriptions = [_desc(1, "a", "A parked bus")]

    report = build_report(descriptions)

    matched = [s.text for s in report.scenes[0].entries[0].segments if s.matched]
    assert matched == ["parked"]


def test_build_report_without_reference_leaves_scores_empty() -> None:
    descriptions = [_desc(1, "a", "a truck", reference=None)]

    report = build_report(descriptions)

    assert report.scene_scores[0].score is None
    assert report.models[0].f1 is None


def test_build_report_rejects_duplicate_model_for_a_scene() -> None:
    descriptions = [_desc(1, "a", "x"), _desc(1, "a", "y")]

    with pytest.raises(ValueError, match="more than once"):
        build_report(descriptions)


def test_render_html_embeds_the_report_data_and_each_image_as_the_caller_resolves_it() -> None:
    report = build_report([_desc(1, "a", "</script> truck")])

    html = render_html(report, None, lambda image_path: f"resolved:{image_path}")

    assert "resolved:/img/1.jpg" in html
    assert "<\\/script> truck" in html
    assert json.loads(html.split('type="application/json">')[1].split("</script>")[0])["models"][0]["model_name"] == "a"


def test_render_html_embeds_the_api_url_only_when_given() -> None:
    report = build_report([_desc(1, "a", "truck")])

    live = render_html(report, "http://api:1", str)
    static = render_html(report, None, str)

    assert '"api_url": "http://api:1"' in live
    assert '"api_url": null' in static


def test_build_report_keeps_each_camera_of_a_scene_as_its_own_row() -> None:
    descriptions = [
        _desc(1, "a", "x", camera="CAM_FRONT"),
        _desc(1, "a", "y", camera="CAM_BACK"),
        _desc(1, "b", "z", camera="CAM_BACK"),
    ]

    report = build_report(descriptions)

    assert [(s.scene_name, s.camera_channel) for s in report.scenes] == [
        ("scene-0001", "CAM_BACK"),
        ("scene-0001", "CAM_FRONT"),
    ]
    assert [e.model_name for e in report.scenes[0].entries] == ["a", "b"]
    assert report.cameras == ["CAM_BACK", "CAM_FRONT"]


def test_build_report_still_rejects_the_same_model_twice_on_one_camera() -> None:
    descriptions = [_desc(1, "a", "x", camera="CAM_BACK"), _desc(1, "a", "y", camera="CAM_BACK")]

    with pytest.raises(ValueError, match=r"CAM_BACK.*more than once"):
        build_report(descriptions)


def test_build_report_scores_a_scene_once_per_model_over_all_its_cameras() -> None:
    reference = "parked truck, turn left"
    descriptions = [
        _desc(1, "a", "a parked truck", reference, camera="CAM_FRONT"),
        _desc(1, "a", "a left turn", reference, camera="CAM_BACK"),
    ]

    report = build_report(descriptions)

    [scene_score] = report.scene_scores
    assert scene_score.cameras == 2
    assert scene_score.score is not None
    assert scene_score.score.recall == 1.0
    assert report.models[0].scenes == 1
