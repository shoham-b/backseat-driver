"""Renders a `Report` as one self-contained HTML file: data, images, styles and script all inline.

Keyframe images are embedded as base64 so the file can be opened or shared without the dataset. Where the bytes come
from is up to the caller: the local file at `image_path` by default, or the API for a report built from jobs.
"""

import base64
import json
import mimetypes
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


def write_html(
    report: Report,
    path: str,
    api_url: str | None = None,
    read_image: Callable[[str], str] | None = None,
) -> None:
    """Write `report` to `path` with its images embedded. `read_image` turns an `image_path` into a `data:` URI
    (default: read the local file, raising FileNotFoundError if it is missing)."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(report, api_url, read_image or file_data_uri), encoding="utf-8")


def file_data_uri(image_path: str) -> str:
    image = Path(image_path)
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(image.read_bytes()).decode('ascii')}"
