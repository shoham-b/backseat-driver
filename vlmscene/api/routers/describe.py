"""On-demand captioning endpoint — describe a single uploaded image.

Demonstrates deploying the same bl.captioner.Captioner used by the batch CLI
pipeline as a small inference service, instead of (or alongside) running the
CLI as a scheduled batch job.
"""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from vlmscene.api.dependencies import get_captioner
from vlmscene.bl.captioner import Captioner
from vlmscene.bl.errors import UnprocessableError

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
            # Inference is synchronous/CPU-bound — off the event loop so one
            # slow request doesn't stall every other request being served.
            description = await run_in_threadpool(captioner.caption, str(tmp_path))
        except Exception as exc:
            raise UnprocessableError(f"could not read image: {exc}") from exc

    return DescribeResponse(description=description, model_name=captioner.model_name)
