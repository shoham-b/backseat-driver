from fastapi import Request

from vlmscene.bl.captioner import Captioner


def get_captioner(request: Request) -> Captioner:
    return request.app.state.captioner  # type: ignore[no-any-return]
