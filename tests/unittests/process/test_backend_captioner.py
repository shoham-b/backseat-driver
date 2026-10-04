from backseat_driver.process.backend_captioner import BackendCaptioner
from backseat_driver.process.backends.backend import CaptionBackend
from backseat_driver.process.model import CaptionModel


class _RecordingBackend(CaptionBackend):
    def __init__(self) -> None:
        self.loaded: list[CaptionModel] = []
        self.generated: list[tuple[str, CaptionModel]] = []

    def load(self, model: CaptionModel) -> None:
        self.loaded.append(model)

    def generate(self, image_path: str, model: CaptionModel) -> str:
        self.generated.append((image_path, model))
        return "a caption"

    def healthcheck(self) -> bool:
        return False


def test_model_name_comes_from_the_model() -> None:
    captioner = BackendCaptioner(_RecordingBackend(), CaptionModel("some/model"))

    assert captioner.model_name == "some/model"


def test_caption_runs_the_model_on_the_backend() -> None:
    backend = _RecordingBackend()
    model = CaptionModel("some/model", prompt="describe")
    captioner = BackendCaptioner(backend, model)

    description = captioner.caption("scene.png")

    assert description == "a caption"
    assert backend.generated == [("scene.png", model)]


def test_load_and_healthcheck_delegate_to_the_backend() -> None:
    backend = _RecordingBackend()
    model = CaptionModel("some/model")
    captioner = BackendCaptioner(backend, model)

    captioner.load()

    assert backend.loaded == [model]
    assert captioner.healthcheck() is False
