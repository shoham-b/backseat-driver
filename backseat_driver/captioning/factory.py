"""Builds the configured `Captioner` so the API, CLI and workers pick a backend and model the same way."""

from backseat_driver.captioning.anthropic_backend import AnthropicBackend
from backseat_driver.captioning.backend import CaptionBackend
from backseat_driver.captioning.backend_captioner import BackendCaptioner
from backseat_driver.captioning.captioner import Captioner
from backseat_driver.captioning.huggingface_backend import HuggingFaceBackend
from backseat_driver.captioning.model import CaptionModel
from backseat_driver.captioning.ollama_backend import OllamaBackend
from backseat_driver.config import Settings, VlmBackend


def build_backend(settings: Settings, backend: VlmBackend) -> CaptionBackend:
    """Return the runtime for `backend`, independent of which model it will run."""
    if backend is VlmBackend.HUGGINGFACE:
        return HuggingFaceBackend()
    if backend is VlmBackend.OLLAMA:
        return OllamaBackend(base_url=settings.ollama_url)
    # `build_captioner` rejects unknown backends via `model_name_for`, so only Anthropic is left.
    if settings.anthropic_api_key is None:
        raise ValueError("BACKSEAT_DRIVER_ANTHROPIC_API_KEY must be set to use the anthropic backend")
    return AnthropicBackend(api_key=settings.anthropic_api_key.get_secret_value())


def build_captioner(settings: Settings, backend: VlmBackend | None = None, model_name: str | None = None) -> Captioner:
    """Return the captioner for `backend` (default: `settings.vlm_backend`).

    `model_name` overrides the backend's configured model.
    """
    backend = backend or settings.vlm_backend
    model = CaptionModel(name=settings.model_name_for(backend, model_name))
    return BackendCaptioner(build_backend(settings, backend), model)
