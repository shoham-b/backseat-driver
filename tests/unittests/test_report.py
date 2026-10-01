import json
from pathlib import Path

import pytest

from backseat_driver.adapters.html_report_writer import write_html
from backseat_driver.bl.report import build_report
from backseat_driver.models import SceneDescription


def _desc(scene: int, model: str, text: str, reference: str | None = "parked truck") -> SceneDescription:
    return SceneDescription(
        scene_token=f"token-{scene}",
        scene_name=f"scene-{scene:04d}",
        camera_channel="CAM_FRONT",
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

    assert report.scenes[0].entries[0].score is None
    assert report.models[0].f1 is None


def test_build_report_rejects_duplicate_model_for_a_scene() -> None:
    descriptions = [_desc(1, "a", "x"), _desc(1, "a", "y")]

    with pytest.raises(ValueError, match="more than once"):
        build_report(descriptions)


def test_write_html_embeds_data_and_image(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"\xff\xd8fake")
    description = _desc(1, "a", "</script> truck").model_copy(update={"image_path": str(image)})
    output = tmp_path / "out" / "report.html"

    write_html(build_report([description]), str(output))

    html = output.read_text(encoding="utf-8")
    assert "data:image/jpeg;base64," in html
    assert "<\\/script> truck" in html
    assert json.loads(html.split('type="application/json">')[1].split("</script>")[0])["models"][0]["model_name"] == "a"


def test_write_html_fails_fast_on_missing_image(tmp_path: Path) -> None:
    report = build_report([_desc(1, "a", "truck")])

    with pytest.raises(FileNotFoundError):
        write_html(report, str(tmp_path / "report.html"))
