"""Keyframe images, so a client needs no access to the dataset itself, only to the API.

The report UI inlines the images of the jobs it shows from here. The same key (`samples/CAM_FRONT/<name>.jpg`, what a
description's `image_path` holds) works whether the dataset is a local dataroot or a bucket.
"""

import hashlib
import mimetypes
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from backseat_driver.api.dependencies import get_image_service
from backseat_driver.datasets.image_service import ImageService

router = APIRouter(tags=["images"])

# Dataset images never change under their key, so browsers and proxies may keep them.
_CACHE_CONTROL = "public, max-age=86400, immutable"


@router.get("/images/{key:path}", responses={HTTPStatus.NOT_MODIFIED: {"description": "The client's copy is current"}})
async def get_image(
    key: str, request: Request, images: Annotated[ImageService, Depends(get_image_service)]
) -> Response:
    """A keyframe image by its dataset-relative key. Answers `304` to a matching `If-None-Match`."""
    # The service reads from a store (a file or S3), which blocks, so it stays off the event loop.
    data = await run_in_threadpool(images.read, key)
    etag = f'"{hashlib.sha256(data).hexdigest()[:32]}"'
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)
    return Response(content=data, media_type=mimetypes.guess_type(key)[0], headers=headers)
