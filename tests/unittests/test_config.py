import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.config import Settings, get_settings


def test_defaults() -> None:
    s = Settings()
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8080
    assert s.log_format == "colored"
    assert s.nuscenes_dataroot == "data/sets/nuscenes"
    assert s.nuscenes_version == "v1.0-mini"
    assert s.camera_channel == "CAM_FRONT"
    assert s.vlm_model_name == "Salesforce/blip-image-captioning-base"
    assert s.output_path == "output/scene_descriptions.json"


def test_nuscenes_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKSEAT_DRIVER_NUSCENES_DATAROOT", "/mnt/nuscenes")
    monkeypatch.setenv("BACKSEAT_DRIVER_CAMERA_CHANNEL", "CAM_BACK")

    s = Settings()

    assert s.nuscenes_dataroot == "/mnt/nuscenes"
    assert s.camera_channel == "CAM_BACK"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKSEAT_DRIVER_API_PORT", "9090")
    s = Settings()
    assert s.api_port == 9090


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b


def test_api_url_property() -> None:
    s = Settings(api_host="0.0.0.0", api_port=8000)
    assert s.api_url == "http://0.0.0.0:8000"


@given(port=st.integers(min_value=1, max_value=65535))
def test_api_url_includes_port(port: int) -> None:
    s = Settings(api_port=port)
    assert f":{port}" in s.api_url


@given(host=st.from_regex(r"[a-z0-9][a-z0-9.-]*", fullmatch=True))
def test_api_url_includes_host(host: str) -> None:
    s = Settings(api_host=host)
    assert host in s.api_url
