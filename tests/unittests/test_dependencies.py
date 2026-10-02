from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore


@pytest.mark.parametrize(
    ("getter", "attribute", "instance"),
    [
        (get_captioner, "captioner", FakeCaptioner()),
        (get_job_queue, "job_queue", FakeJobQueue()),
        (get_job_store, "job_store", FakeJobStore()),
    ],
)
def test_dependency_returns_the_object_the_lifespan_put_on_app_state(
    getter: Callable[..., object], attribute: str, instance: object
) -> None:
    request = MagicMock()
    setattr(request.app.state, attribute, instance)

    assert getter(request) is instance


def test_dependency_fails_fast_when_the_lifespan_never_ran() -> None:
    class _EmptyState:
        pass

    request = MagicMock()
    request.app.state = _EmptyState()

    with pytest.raises(AttributeError):
        get_job_store(request)
