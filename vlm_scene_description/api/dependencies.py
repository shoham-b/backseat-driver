from fastapi import Request

from vlm_scene_description.bl.captioner import Captioner


def get_captioner(request: Request) -> Captioner:
    return request.app.state.captioner  # type: ignore[no-any-return]
