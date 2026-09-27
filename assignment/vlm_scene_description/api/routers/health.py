from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends

from vlm_scene_description.api.dependencies import get_repository
from vlm_scene_description.api.errors import APIError
from vlm_scene_description.db.base import Repository

router = APIRouter(tags=["observability"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    repository: Annotated[Repository, Depends(get_repository)],

) -> dict[str, str]:
    """Readiness probe — returns 200 only when all dependencies are reachable."""
    if not await repository.healthcheck():
        raise APIError("storage backend unavailable", HTTPStatus.SERVICE_UNAVAILABLE)

    return {"status": "ok"}
