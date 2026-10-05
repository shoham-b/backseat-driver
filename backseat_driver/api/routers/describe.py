"""On-demand captioning endpoint — describe a single uploaded image.

Demonstrates deploying the same captioning.Captioner used by the batch CLI
pipeline as a small inference service, instead of (or alongside) running the
CLI as a scheduled batch job.
"""

import asyncio
import re
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from backseat_driver.api.dependencies import get_captioner, get_upload_dir
from backseat_driver.api.schemas import DescribeResponse
from backseat_driver.errors import UnprocessableError
from backseat_driver.process.captioner import Captioner

_PLAIN_SUFFIX = re.compile(r"\.[a-z0-9]{1,8}")

router = APIRouter(tags=["describe"])


@router.post("/describe")
async def describe(
    image: UploadFile,
    captioner: Annotated[Captioner, Depends(get_captioner)],
    upload_dir: Annotated[Path, Depends(get_upload_dir)],
) -> DescribeResponse:
    """Caption a single uploaded image using the configured VLM.

    An `async def`: reading the upload, writing it and captioning it are all awaited, so none of them stalls the event
    loop (a local model runs on a worker thread inside the captioner).
    """
    contents = await image.read()
    if not contents:
        raise UnprocessableError("uploaded file is empty")

    # The filename is client-controlled, so it never becomes part of the path: only a plain extension survives,
    # because the captioners sniff the image type from it.
    suffix = PurePosixPath((image.filename or "").replace("\\", "/")).suffix.lower()
    tmp_path = upload_dir / f"upload{suffix if _PLAIN_SUFFIX.fullmatch(suffix) else ''}"
    await asyncio.to_thread(tmp_path.write_bytes, contents)
    # A file the model cannot read is the backend's `UnprocessableError` (422); any other failure is the service's own
    # and stays a 500.
    description = await captioner.caption(str(tmp_path))

    return DescribeResponse(description=description, model_name=captioner.model_name)
