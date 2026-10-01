"""Builds the configured `Captioner` so the API, CLI and workers pick a backend the same way."""

from backseat_driver.captioning.anthropic_captioner import AnthropicCaptioner
from backseat_driver.captioning.captioner import Captioner
from backseat_driver.captioning.huggingface_captioner import HuggingFaceCaptioner
from backseat_driver.captioning.ollama_captioner import OllamaCaptioner
from backseat_driver.config import Settings, VlmBackend


def build_captioner(settings: Settings, backend: VlmBackend | None = None, model_name: str | None = None) -> Captioner:
    """Return the captioner for `backend` (default: `settings.vlm_backend`).

    `model_name` overrides the backend's configured model.
    """
    backend = backend or settings.vlm_backend
    if backend is VlmBackend.HUGGINGFACE:
        return HuggingFaceCaptioner(model_name=model_name or settings.vlm_model_name)
    if backend is VlmBackend.OLLAMA:
        return OllamaCaptioner(model_name=model_name or settings.ollama_model_name, base_url=settings.ollama_url)
    if backend is VlmBackend.ANTHROPIC:
        if settings.anthropic_api_key is None:
            raise ValueError("BACKSEAT_DRIVER_ANTHROPIC_API_KEY must be set to use the anthropic backend")
        return AnthropicCaptioner(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model_name=model_name or settings.anthropic_model_name,
        )
    raise ValueError(f"Unknown captioner backend {backend!r}")
