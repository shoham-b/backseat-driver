"""On-demand captioning endpoint — describe a single uploaded image.

Demonstrates deploying the same captioning.Captioner used by the batch CLI
pipeline as a small inference service, instead of (or alongside) running the
CLI as a scheduled batch job.
"""

import re
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from backseat_driver.api.dependencies import get_captioner, get_upload_dir
from backseat_driver.errors import UnprocessableError
from backseat_driver.process.captioner import Captioner

_PLAIN_SUFFIX = re.compile(r"\.[a-z0-9]{1,8}")

router = APIRouter(tags=["describe"])


class DescribeResponse(BaseModel):
    description: str
    model_name: str


@router.post("/describe")
def describe(
    image: UploadFile,
    captioner: Annotated[Captioner, Depends(get_captioner)],
    upload_dir: Annotated[Path, Depends(get_upload_dir)],
) -> DescribeResponse:
    """Caption a single uploaded image using the configured VLM.

    A plain `def`, so FastAPI runs it on a worker thread: inference blocks and must not stall the event loop.
    """
    contents = image.file.read()
    if not contents:
        raise UnprocessableError("uploaded file is empty")

    # The filename is client-controlled, so it never becomes part of the path: only a plain extension survives,
    # because the captioners sniff the image type from it.
    suffix = PurePosixPath((image.filename or "").replace("\\", "/")).suffix.lower()
    tmp_path = upload_dir / f"upload{suffix if _PLAIN_SUFFIX.fullmatch(suffix) else ''}"
    tmp_path.write_bytes(contents)
    try:
        description = captioner.caption(str(tmp_path))
    except Exception as exc:
        raise UnprocessableError(f"could not read image: {exc}") from exc

    return DescribeResponse(description=description, model_name=captioner.model_name)
