from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends

from vlm_scene_description.api.dependencies import get_captioner
from vlm_scene_description.api.errors import APIError
from vlm_scene_description.bl.captioner import Captioner

router = APIRouter(tags=["observability"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    captioner: Annotated[Captioner, Depends(get_captioner)],
) -> dict[str, str]:
    """Readiness probe — returns 200 only when all dependencies are reachable."""
    if not captioner.healthcheck():
        raise APIError("VLM captioner unavailable", HTTPStatus.SERVICE_UNAVAILABLE)

    return {"status": "ok"}
