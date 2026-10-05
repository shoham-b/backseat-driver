"""Turns a set of `DescriptionSource`s into the report page: the one path the CLI and the UI both take."""

from collections.abc import Sequence
from typing import NamedTuple

from backseat_driver.concurrency import gather_all
from backseat_driver.show.description_source import DescriptionSource
from backseat_driver.show.html_report_writer import data_uri, render_html
from backseat_driver.show.report import build_report

# Images fetched at once: enough to overlap the waits, few enough that a slow source is not flooded.
_IMAGE_FETCHES = 8


class RenderedReport(NamedTuple):
    html: str
    description_count: int


class ReportService:
    def __init__(self, sources: Sequence[DescriptionSource], live_api_url: str | None = None) -> None:
        self._sources = sources
        self._live_api_url = live_api_url

    async def render(self, embed_images: bool) -> RenderedReport:
        """Read every source and render the page.

        With `embed_images` every image is inlined, so the page stands alone as a file. Without it, an image its
        source can serve through the UI is linked instead, and only the rest are inlined.
        """
        owned = [(d, source) for source in self._sources for d in await source.descriptions()]
        descriptions = [d for d, _ in owned]
        source_of_image: dict[str, DescriptionSource] = {}
        for d, source in owned:
            source_of_image.setdefault(d.image_path, source)

        async def image_src(image_path: str) -> str:
            source = source_of_image[image_path]
            link = None if embed_images else source.image_link(image_path)
            if link is not None:
                return link
            image = await source.image(image_path)
            return data_uri(image.body, image.content_type)

        # `render_html` asks for each image synchronously, so every one is fetched before it runs.
        paths = list(source_of_image)
        sources = await gather_all((image_src(path) for path in paths), limit=_IMAGE_FETCHES)
        src_of_image = dict(zip(paths, sources, strict=True))

        html = render_html(build_report(descriptions), self._live_api_url, src_of_image.__getitem__)
        return RenderedReport(html, len(descriptions))
