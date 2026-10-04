"""Which image keys may be served to a client.

Both the API and the report UI hand keys from outside (a URL path) to a store, so they share one rule: a key names a
camera keyframe below `samples/`, with an image suffix and nothing that climbs out of it. The metadata tables live in
the same store and must never be reachable through an image URL.
"""

from pathlib import PurePosixPath

from backseat_driver.errors import UnprocessableError

_ALLOWED_PREFIX = "samples/"
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}


def validate_image_key(key: str) -> None:
    """Raise `UnprocessableError` unless `key` is a keyframe image key."""
    if (
        not key.startswith(_ALLOWED_PREFIX)
        or "\\" in key
        or any(part in ("", ".", "..") for part in key.split("/"))
        or PurePosixPath(key).suffix.lower() not in _ALLOWED_SUFFIXES
    ):
        raise UnprocessableError(f"Not a keyframe image key: {key!r}")
