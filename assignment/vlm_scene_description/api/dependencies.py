from fastapi import Request

from vlm_scene_description.db.base import Repository


def get_repository(request: Request) -> Repository:
    return request.app.state.repository  # type: ignore[no-any-return]


