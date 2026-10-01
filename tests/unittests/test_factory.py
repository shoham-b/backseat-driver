import pytest
from pydantic import SecretStr

from backseat_driver.adapters.anthropic_captioner import AnthropicCaptioner
from backseat_driver.adapters.factory import build_captioner
from backseat_driver.adapters.huggingface_captioner import HuggingFaceCaptioner
from backseat_driver.adapters.ollama_captioner import OllamaCaptioner
from backseat_driver.config import Settings, VlmBackend


def test_settings_backend_is_used_when_none_is_given() -> None:
    settings = Settings(vlm_backend=VlmBackend.OLLAMA)

    assert isinstance(build_captioner(settings), OllamaCaptioner)


def test_explicit_backend_wins_over_settings() -> None:
    settings = Settings(vlm_backend=VlmBackend.OLLAMA)

    assert isinstance(build_captioner(settings, backend=VlmBackend.HUGGINGFACE), HuggingFaceCaptioner)


def test_huggingface_uses_configured_model_and_override() -> None:
    settings = Settings(vlm_model_name="configured/model")

    configured = build_captioner(settings)
    overridden = build_captioner(settings, model_name="other/model")

    assert (configured.model_name, overridden.model_name) == ("configured/model", "other/model")


def test_anthropic_uses_configured_model_and_override() -> None:
    settings = Settings(anthropic_api_key=SecretStr("k"), anthropic_model_name="claude-a")

    configured = build_captioner(settings, backend=VlmBackend.ANTHROPIC)
    overridden = build_captioner(settings, backend=VlmBackend.ANTHROPIC, model_name="claude-b")

    assert isinstance(configured, AnthropicCaptioner)
    assert (configured.model_name, overridden.model_name) == ("claude-a", "claude-b")


def test_unknown_backend_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown captioner backend"):
        build_captioner(Settings(), backend="bogus")  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("backend", list(VlmBackend))
def test_every_declared_backend_is_buildable(backend: VlmBackend) -> None:
    settings = Settings(anthropic_api_key=SecretStr("k"))

    assert build_captioner(settings, backend=backend).model_name
