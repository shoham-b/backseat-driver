from collections.abc import Callable
from http import HTTPStatus
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backseat_driver.api.dependencies import get_captioner, get_upload_dir
from backseat_driver.errors import UnprocessableError
from backseat_driver.process.captioner import Captioner
from tests.fakes import FakeCaptioner
from tests.integrationtests.conftest import ClientFactory


class _RecordingCaptioner(FakeCaptioner):
    """Records what was on disk at the moment the model was asked to read the image."""

    def __init__(self) -> None:
        super().__init__("recorded")
        self.contents: list[bytes] = []
        self.seen_resolved: list[Path] = []

    def caption(self, image_path: str) -> str:
        self.contents.append(Path(image_path).read_bytes())
        self.seen_resolved.append(Path(image_path).resolve())
        return super().caption(image_path)


class _RejectingCaptioner(FakeCaptioner):
    def caption(self, image_path: str) -> str:
        raise UnprocessableError("cannot identify image file")


class _BrokenCaptioner(FakeCaptioner):
    def caption(self, image_path: str) -> str:
        raise RuntimeError("model server exploded")


def _install(
    client_with: ClientFactory,
    captioner: Captioner,
    upload_dir: Path | None = None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    overrides: dict[Callable[..., object], Callable[..., object]] = {get_captioner: lambda: captioner}
    if upload_dir is not None:
        overrides[get_upload_dir] = lambda: upload_dir
    return client_with(overrides, raise_server_exceptions=raise_server_exceptions)


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), color="green").save(buf, format="PNG")
    return buf.getvalue()


def test_the_captioner_reads_the_uploaded_bytes(client_with: ClientFactory) -> None:
    captioner = _RecordingCaptioner()
    client = _install(client_with, captioner)
    payload = _png()

    response = client.post("/describe", files={"image": ("scene.png", payload, "image/png")})

    assert response.status_code == HTTPStatus.OK
    assert captioner.contents == [payload]


def test_the_upload_is_removed_once_the_request_completes(client_with: ClientFactory) -> None:
    captioner = FakeCaptioner()
    client = _install(client_with, captioner)

    client.post("/describe", files={"image": ("scene.png", _png(), "image/png")})

    [seen] = captioner.seen_paths
    assert not Path(seen).exists()
    assert not Path(seen).parent.exists()


def test_the_temp_file_keeps_the_upload_suffix(client_with: ClientFactory) -> None:
    captioner = FakeCaptioner()
    client = _install(client_with, captioner)

    client.post("/describe", files={"image": ("photo.jpeg", _png(), "image/jpeg")})

    assert captioner.seen_paths[0].endswith(".jpeg")


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.png",
        "..\\escape.png",
        "/etc/escape.png",
        "a/b/../../../escape.png",
        "..",
        "x/..",
        "D:x.png",
        "NUL.png",
    ],
)
def test_a_hostile_filename_cannot_place_the_upload_outside_the_temp_directory(
    client_with: ClientFactory, tmp_path: Path, filename: str
) -> None:
    captioner = _RecordingCaptioner()
    client = _install(client_with, captioner, upload_dir=tmp_path)

    response = client.post("/describe", files={"image": (filename, _png(), "image/png")})

    assert response.status_code == HTTPStatus.OK
    assert [p.parent for p in captioner.seen_resolved] == [tmp_path.resolve()]
    assert [p.name for p in tmp_path.iterdir()] == [Path(captioner.seen_paths[0]).name]


@pytest.mark.parametrize(
    ("filename", "expected_suffix"),
    [("photo.PNG", ".png"), ("noextension", ""), ("archive.tar.gz", ".gz"), ("evil.png:stream", ""), ("x.p ng", "")],
)
def test_only_a_plain_extension_of_the_filename_reaches_the_captioner(
    client_with: ClientFactory, filename: str, expected_suffix: str
) -> None:
    captioner = FakeCaptioner()
    client = _install(client_with, captioner)

    client.post("/describe", files={"image": (filename, _png(), "image/png")})

    assert Path(captioner.seen_paths[0]).name == f"upload{expected_suffix}"


def test_an_image_the_captioner_rejects_is_reported_as_unprocessable_with_the_reason(
    client_with: ClientFactory,
) -> None:
    client = _install(client_with, _RejectingCaptioner())

    response = client.post("/describe", files={"image": ("scene.png", b"not an image", "image/png")})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "cannot identify image file" in error["message"]


def test_a_captioner_failure_that_is_not_about_the_image_is_a_server_error(client_with: ClientFactory) -> None:
    client = _install(client_with, _BrokenCaptioner(), raise_server_exceptions=False)

    response = client.post("/describe", files={"image": ("scene.png", _png(), "image/png")})

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["error"]["message"] == "internal server error"


def test_the_failed_upload_is_still_cleaned_up(client_with: ClientFactory) -> None:
    seen: list[str] = []

    class _Failing(FakeCaptioner):
        def caption(self, image_path: str) -> str:
            seen.append(image_path)
            raise ValueError("bad")

    client = _install(client_with, _Failing(), raise_server_exceptions=False)

    client.post("/describe", files={"image": ("scene.png", _png(), "image/png")})

    assert not Path(seen[0]).exists()


def test_the_missing_image_field_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/describe")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_a_non_file_image_field_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/describe", data={"image": "just text"})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_an_empty_upload_never_reaches_the_captioner(client_with: ClientFactory) -> None:
    captioner = FakeCaptioner()
    client = _install(client_with, captioner)

    response = client.post("/describe", files={"image": ("empty.png", b"", "image/png")})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "empty" in response.json()["error"]["message"]
    assert captioner.seen_paths == []


def test_the_response_reports_the_model_that_produced_the_caption(client_with: ClientFactory) -> None:
    client = _install(client_with, FakeCaptioner("a rainy road"))

    body = client.post("/describe", files={"image": ("s.png", _png(), "image/png")}).json()

    assert body == {"description": "a rainy road", "model_name": "fake-model"}


def test_the_ui_origin_may_call_describe_from_the_browser(client: TestClient) -> None:
    response = client.options(
        "/describe",
        headers={"Origin": "http://127.0.0.1:8081", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8081"


def test_an_unknown_origin_is_not_granted_browser_access(client: TestClient) -> None:
    response = client.options(
        "/describe",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_get_is_not_allowed_on_describe(client: TestClient) -> None:
    assert client.get("/describe").status_code == HTTPStatus.METHOD_NOT_ALLOWED
