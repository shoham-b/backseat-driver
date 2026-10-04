from collections.abc import Callable

import pytest
from fastapi import FastAPI, Request
from starlette.datastructures import State

from backseat_driver.api.dependencies import (
    get_app_settings,
    get_app_state,
    get_captioner,
    get_image_store,
    get_job_queue,
    get_job_store,
)
from backseat_driver.api.state import AppState
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, make_settings


def _request_to(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app})


def _state() -> AppState:
    return AppState(make_settings(), FakeCaptioner(), FakeImageStore(), FakeJobQueue(), FakeJobStore())


@pytest.mark.parametrize(
    ("getter", "attribute"),
    [
        (get_app_settings, "settings"),
        (get_captioner, "captioner"),
        (get_image_store, "image_store"),
        (get_job_queue, "job_queue"),
        (get_job_store, "job_store"),
    ],
)
def test_dependency_returns_its_part_of_the_state_the_lifespan_built(
    getter: Callable[[AppState], object], attribute: str
) -> None:
    state = _state()

    assert getter(state) is getattr(state, attribute)


def test_app_state_is_what_the_lifespan_put_on_the_app() -> None:
    app = FastAPI()
    state = _state()
    app.state = State({"services": state})

    assert get_app_state(_request_to(app)) is state


def test_app_state_fails_fast_when_the_lifespan_never_ran() -> None:
    with pytest.raises(AttributeError):
        get_app_state(_request_to(FastAPI()))
