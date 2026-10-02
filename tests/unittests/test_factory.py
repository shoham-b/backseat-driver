import pytest
from pydantic import SecretStr

from backseat_driver.captioning.anthropic_backend import AnthropicBackend
from backseat_driver.captioning.factory import build_backend, build_captioner
from backseat_driver.captioning.huggingface_backend import HuggingFaceBackend
from backseat_driver.captioning.ollama_backend import OllamaBackend
from backseat_driver.config import Settings, VlmBackend


def test_settings_backend_is_used_when_none_is_given() -> None:
    settings = Settings(vlm_backend=VlmBackend.OLLAMA)

    captioner = build_captioner(settings)

    assert captioner.model_name == settings.ollama_model_name


def test_huggingface_uses_configured_model_and_override() -> None:
    settings = Settings(vlm_model_name="configured/model")

    configured = build_captioner(settings)
    overridden = build_captioner(settings, model_name="other/model")

    assert (configured.model_name, overridden.model_name) == ("configured/model", "other/model")


def test_ollama_uses_configured_model_and_override() -> None:
    settings = Settings(ollama_model_name="llama3.2-vision")

    configured = build_captioner(settings, backend=VlmBackend.OLLAMA)
    overridden = build_captioner(settings, backend=VlmBackend.OLLAMA, model_name="bakllava")

    assert (configured.model_name, overridden.model_name) == ("llama3.2-vision", "bakllava")


def test_anthropic_uses_configured_model_and_override() -> None:
    settings = Settings(anthropic_api_key=SecretStr("k"), anthropic_model_name="claude-a")

    configured = build_captioner(settings, backend=VlmBackend.ANTHROPIC)
    overridden = build_captioner(settings, backend=VlmBackend.ANTHROPIC, model_name="claude-b")

    assert (configured.model_name, overridden.model_name) == ("claude-a", "claude-b")


def test_anthropic_requires_api_key() -> None:
    settings = Settings(anthropic_api_key=None)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_captioner(settings, backend=VlmBackend.ANTHROPIC)


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        (VlmBackend.HUGGINGFACE, HuggingFaceBackend),
        (VlmBackend.OLLAMA, OllamaBackend),
        (VlmBackend.ANTHROPIC, AnthropicBackend),
    ],
)
def test_build_backend_selects_runtime_independent_of_model(backend: VlmBackend, expected: type) -> None:
    settings = Settings(anthropic_api_key=SecretStr("k"))

    assert isinstance(build_backend(settings, backend), expected)


def test_unknown_backend_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown captioner backend"):
        build_captioner(Settings(), backend="bogus")  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("backend", list(VlmBackend))
def test_every_declared_backend_is_buildable(backend: VlmBackend) -> None:
    settings = Settings(anthropic_api_key=SecretStr("k"))

    assert build_captioner(settings, backend=backend).model_name
