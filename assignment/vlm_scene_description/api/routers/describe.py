"""On-demand captioning endpoint — describe a single uploaded image.

Demonstrates deploying the same bl.captioner.Captioner used by the batch CLI
pipeline as a small inference service, instead of (or alongside) running the
CLI as a scheduled batch job.
"""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from vlm_scene_description.api.dependencies import get_captioner
from vlm_scene_description.bl.captioner import Captioner
from vlm_scene_description.bl.errors import UnprocessableError

router = APIRouter(tags=["describe"])


class DescribeResponse(BaseModel):
    description: str
    model_name: str


@router.post("/describe")
async def describe(
    image: UploadFile,
    captioner: Annotated[Captioner, Depends(get_captioner)],
) -> DescribeResponse:
    """Caption a single uploaded image using the configured VLM."""
    contents = await image.read()
    if not contents:
        raise UnprocessableError("uploaded file is empty")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / (image.filename or "upload")
        tmp_path.write_bytes(contents)
        try:
            description = captioner.caption(str(tmp_path))
        except Exception as exc:
            raise UnprocessableError(f"could not read image: {exc}") from exc

    model_name = getattr(captioner, "model_name", "unknown")
    return DescribeResponse(description=description, model_name=model_name)
