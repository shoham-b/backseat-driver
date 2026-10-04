import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.show.metrics import content_words, score


def test_content_words_drops_stopwords_and_folds_plurals() -> None:
    words = content_words("The Trucks are parked at an intersection")

    assert words == {"truck", "parked", "intersection"}


def test_score_full_overlap_is_perfect() -> None:
    result = score("parked truck", "Parked truck")

    assert (result.precision, result.recall, result.f1) == (1.0, 1.0, 1.0)


def test_score_verbose_description_has_full_recall_but_low_precision() -> None:
    result = score("a parked truck beside a busy road with several cyclists", "parked truck")

    assert result.recall == 1.0
    assert result.precision == pytest.approx(2 / 7)


def test_score_without_overlap_is_zero() -> None:
    result = score("sunny beach", "parked truck")

    assert result.f1 == 0.0


def test_score_rejects_reference_without_content_words() -> None:
    with pytest.raises(ValueError, match="no content words"):
        score("a truck", "the of a")


@given(description=st.text(), reference=st.text(alphabet=st.characters(codec="ascii"), min_size=1))
def test_score_metrics_stay_within_unit_interval(description: str, reference: str) -> None:
    if not content_words(reference):
        return

    result = score(description, reference)

    assert 0.0 <= result.precision <= 1.0
    assert 0.0 <= result.recall <= 1.0
    assert 0.0 <= result.f1 <= 1.0
