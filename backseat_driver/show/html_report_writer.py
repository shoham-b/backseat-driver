"""Renders a `Report` as one self-contained HTML file: data, images, styles and script all inline.

Keyframe images are embedded as base64 so the file can be opened or shared without the dataset. What goes in each
`<img src>` is up to the caller (see `ReportService`).
"""

import base64
import json
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

from backseat_driver.show.report import Report


def load_template() -> str:
    """The report page, with `__REPORT_DATA__` marking where the report JSON goes."""
    return files(__package__).joinpath("report_template.html").read_text(encoding="utf-8")


def render_html(report: Report, api_url: str | None, read_image: Callable[[str], str]) -> str:
    """The report page. `read_image` turns a scene's `image_path` into what its `<img src>` should be: a `data:` URI
    for a self-contained file, or a URL the serving process answers.

    With `api_url`, the page gets a "try it live" card that uploads an image to that API's `/describe`.
    """
    payload = report.model_dump(mode="json")
    for scene in payload["scenes"]:
        scene["image"] = read_image(scene["image_path"])
    payload["api_url"] = api_url
    # "</" would end the surrounding <script> tag early.
    data = json.dumps(payload).replace("</", "<\\/")
    return load_template().replace("__REPORT_DATA__", data)


def save_html(html: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def data_uri(body: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(body).decode('ascii')}"
