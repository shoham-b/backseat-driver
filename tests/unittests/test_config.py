from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.config import RunMode, Settings, VlmBackend, get_settings
from tests.fakes import keyword_settings


def test_defaults() -> None:
    s = keyword_settings()
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8080
    assert s.log_format == "colored"
    assert s.nuscenes_dataroot == "data/sets/nuscenes"
    assert s.nuscenes_version == "v1.0-mini"
    assert s.camera_channel == "CAM_FRONT"
    assert s.output_dir == "output"


def _settings_from_env_file(tmp_path: Path, **variables: str) -> Settings:
    """Settings read from a dotenv file, so the prefix/parsing is tested without touching os.environ."""
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"BACKSEAT_DRIVER_{name.upper()}={value}\n" for name, value in variables.items()))
    return Settings(_env_file=env_file)


def test_nuscenes_env_override(tmp_path: Path) -> None:
    s = _settings_from_env_file(tmp_path, nuscenes_dataroot="/mnt/nuscenes", camera_channel="CAM_BACK")

    assert s.nuscenes_dataroot == "/mnt/nuscenes"
    assert s.camera_channel == "CAM_BACK"


def test_env_override(tmp_path: Path) -> None:
    s = _settings_from_env_file(tmp_path, api_port="9090")
    assert s.api_port == 9090


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b


def test_api_url_property() -> None:
    s = keyword_settings(api_host="0.0.0.0", api_port=8000)
    assert s.api_url == "http://0.0.0.0:8000"


@given(port=st.integers(min_value=1, max_value=65535))
def test_api_url_includes_port(port: int) -> None:
    s = keyword_settings(api_port=port)
    assert f":{port}" in s.api_url


@given(host=st.from_regex(r"[a-z0-9][a-z0-9.-]*", fullmatch=True))
def test_api_url_includes_host(host: str) -> None:
    s = keyword_settings(api_host=host)
    assert host in s.api_url


def test_default_output_path_is_inferred_from_backend_and_configured_model() -> None:
    s = keyword_settings(vlm_model_name="Salesforce/blip-image-captioning-base")

    assert s.output_path_for() == "output/huggingface__Salesforce-blip-image-captioning-base.json"


def test_output_path_follows_selected_backend_and_model() -> None:
    s = keyword_settings(output_dir="results", anthropic_model_name="claude-haiku-4-5-20251001")

    assert s.output_path_for(VlmBackend.OLLAMA, "llava:13b") == "results/ollama__llava-13b.json"
    assert s.output_path_for(VlmBackend.ANTHROPIC) == "results/anthropic__claude-haiku-4-5-20251001.json"


def test_model_name_for_prefers_explicit_override() -> None:
    s = keyword_settings(ollama_model_name="llava")

    assert s.model_name_for(VlmBackend.OLLAMA) == "llava"
    assert s.model_name_for(VlmBackend.OLLAMA, "bakllava") == "bakllava"


@pytest.mark.parametrize("backend", list(VlmBackend))
def test_model_name_for_fails_fast_when_no_model_is_chosen(backend: VlmBackend) -> None:
    s = keyword_settings(vlm_model_name=None, ollama_model_name=None, anthropic_model_name=None)

    with pytest.raises(ValueError, match=f"No model chosen for the {backend.value} backend"):
        s.model_name_for(backend)


@given(model=st.text(min_size=1))
def test_output_path_filename_is_always_safe(model: str) -> None:
    path = keyword_settings().output_path_for(VlmBackend.OLLAMA, model)

    assert path.startswith("output/ollama__")
    assert "/" not in path.removeprefix("output/")


def test_ui_defaults_to_loopback_on_8081() -> None:
    s = keyword_settings()

    assert (s.ui_host, s.ui_port) == ("127.0.0.1", 8081)


def test_ui_bind_address_is_read_from_the_environment(tmp_path: Path) -> None:
    s = _settings_from_env_file(tmp_path, ui_host="0.0.0.0", ui_port="9000")

    assert (s.ui_host, s.ui_port) == ("0.0.0.0", 9000)


def test_allowed_origins_default_to_the_ui_page() -> None:
    s = keyword_settings()

    assert s.cors_origins == ["http://127.0.0.1:8081", "http://localhost:8081"]


def test_allowed_origins_follow_the_ui_address() -> None:
    s = keyword_settings(ui_host="0.0.0.0", ui_port=9000)

    assert s.cors_origins == ["http://127.0.0.1:9000", "http://localhost:9000", "http://0.0.0.0:9000"]


def test_cors_origins_override_the_derived_origins() -> None:
    s = keyword_settings(cors_origins=["https://example.com"])

    assert s.cors_origins == ["https://example.com"]


def test_the_distributed_mode_cannot_be_configured_without_a_dataset_bucket() -> None:
    with pytest.raises(ValueError, match="BACKSEAT_DRIVER_DATASET_BUCKET"):
        keyword_settings(mode=RunMode.DISTRIBUTED)


def test_the_monolith_needs_no_dataset_bucket() -> None:
    assert keyword_settings(mode=RunMode.MONOLITH).dataset_bucket is None


def test_the_distributed_mode_is_configured_with_a_bucket() -> None:
    assert keyword_settings(mode=RunMode.DISTRIBUTED, dataset_bucket="nuscenes").dataset_bucket == "nuscenes"
