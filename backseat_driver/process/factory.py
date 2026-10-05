"""Builds the configured `Captioner` so the API, CLI and workers pick a backend and model the same way."""

from backseat_driver.config import Settings, VlmBackend
from backseat_driver.process.backend_captioner import BackendCaptioner
from backseat_driver.process.backends.anthropic import AnthropicBackend
from backseat_driver.process.backends.backend import CaptionBackend
from backseat_driver.process.backends.huggingface import HuggingFaceBackend
from backseat_driver.process.backends.ollama import OllamaBackend
from backseat_driver.process.captioner import Captioner
from backseat_driver.process.http_client import HttpClient, HttpxHttpClient
from backseat_driver.process.model import CaptionModel


def build_http_client() -> HttpClient:
    """The one HTTP client a process shares. It connects on first use; its owner closes it with `aclose`."""
    return HttpxHttpClient()


def build_backend(settings: Settings, http: HttpClient, backend: VlmBackend) -> CaptionBackend:
    """Return the runtime for `backend`, independent of which model it will run."""
    if backend is VlmBackend.HUGGINGFACE:
        return HuggingFaceBackend()
    if backend is VlmBackend.OLLAMA:
        return OllamaBackend(http, base_url=settings.ollama_url)
    # `build_captioner` rejects unknown backends via `model_name_for`, so only Anthropic is left.
    if settings.anthropic_api_key is None:
        raise ValueError("BACKSEAT_DRIVER_ANTHROPIC_API_KEY must be set to use the anthropic backend")
    return AnthropicBackend(http, api_key=settings.anthropic_api_key.get_secret_value())


def build_captioner(
    settings: Settings, http: HttpClient, backend: VlmBackend | None = None, model_name: str | None = None
) -> Captioner:
    """Return the captioner for `backend` (default: `settings.vlm_backend`), its HTTP calls going through `http`.

    `model_name` overrides the backend's configured model.
    """
    backend = backend or settings.vlm_backend
    model = CaptionModel(name=settings.model_name_for(backend, model_name))
    return BackendCaptioner(build_backend(settings, http, backend), model)
