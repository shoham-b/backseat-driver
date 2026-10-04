import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.models import JobState
from backseat_driver.write.job_store.job_store import derive_state


def test_state_is_pending_until_expected_scenes_are_known() -> None:
    assert derive_state(None, 0, None) == JobState.PENDING


def test_state_is_running_while_scenes_remain() -> None:
    assert derive_state(3, 2, None) == JobState.RUNNING


@pytest.mark.parametrize(("expected", "completed"), [(0, 0), (3, 3)])
def test_state_is_completed_when_all_scenes_are_done(expected: int, completed: int) -> None:
    assert derive_state(expected, completed, None) == JobState.COMPLETED


@pytest.mark.parametrize(("expected", "completed"), [(None, 0), (3, 1), (3, 3)])
def test_a_recorded_error_makes_the_job_failed_whatever_the_progress(expected: int | None, completed: int) -> None:
    assert derive_state(expected, completed, "boom") == JobState.FAILED


@given(expected=st.integers(min_value=0, max_value=1000), completed=st.integers(min_value=0, max_value=1000))
def test_state_is_completed_iff_completed_reaches_expected(expected: int, completed: int) -> None:
    state = derive_state(expected, completed, None)

    assert (state == JobState.COMPLETED) == (completed >= expected)
