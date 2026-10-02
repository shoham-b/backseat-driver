"""Renders a `Report` as one self-contained HTML file: data, images, styles and script all inline.

Keyframe images are embedded as base64 so the file can be opened or shared without the dataset.
"""

import base64
import json
import mimetypes
from pathlib import Path

from backseat_driver.reporting.report import Report
from backseat_driver.reporting.report_template import TEMPLATE


def write_html(report: Report, path: str, api_url: str | None = None) -> None:
    """Write `report` to `path`. Raises FileNotFoundError if a scene image is missing.

    With `api_url`, the page gets a "try it live" card that uploads an image to that API's `/describe`.
    """
    payload = report.model_dump(mode="json")
    for scene in payload["scenes"]:
        scene["image"] = _data_uri(Path(scene["image_path"]))
    payload["api_url"] = api_url
    # "</" would end the surrounding <script> tag early.
    data = json.dumps(payload).replace("</", "<\\/")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(TEMPLATE.replace("__REPORT_DATA__", data), encoding="utf-8")


def _data_uri(image: Path) -> str:
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(image.read_bytes()).decode('ascii')}"
