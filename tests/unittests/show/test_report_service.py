from backseat_driver.models import SceneDescription
from backseat_driver.show.report_service import ReportService
from tests.fakes import FakeDescriptionSource


def _desc(path: str, model: str = "m") -> SceneDescription:
    return SceneDescription(
        scene_token=path,
        scene_name=path,
        camera_channel="CAM_FRONT",
        image_path=path,
        description="a truck",
        model_name=model,
    )


def test_every_sources_descriptions_are_counted() -> None:
    service = ReportService([FakeDescriptionSource([_desc("a")]), FakeDescriptionSource([_desc("b")])])

    rendered = service.render(embed_images=True)

    assert rendered.description_count == 2


def test_embedding_inlines_even_the_images_a_source_could_link() -> None:
    service = ReportService([FakeDescriptionSource([_desc("a")], link_prefix="/images/")])

    html = service.render(embed_images=True).html

    assert "data:image/test;base64," in html
    assert "/images/a" not in html


def test_linking_uses_the_sources_link_and_inlines_the_rest() -> None:
    linked = FakeDescriptionSource([_desc("a")], link_prefix="/images/")
    local = FakeDescriptionSource([_desc("b")])

    html = ReportService([linked, local]).render(embed_images=False).html

    assert '"image": "/images/a"' in html
    assert '"image": "data:image/test;base64,' in html


def test_the_live_api_url_reaches_the_page() -> None:
    service = ReportService([FakeDescriptionSource([_desc("a")])], live_api_url="http://api:1")

    html = service.render(embed_images=True).html

    assert '"api_url": "http://api:1"' in html
