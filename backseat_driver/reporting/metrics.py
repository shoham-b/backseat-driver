"""Lexical scoring of a model description against nuScenes' human-written scene label.

nuScenes labels are terse keyword lists ("Parked truck, construction, intersection, turn left"),
so we score *content-word overlap*, not fluency. Precision punishes padding, recall rewards
covering what the label mentions, F1 balances them. Synonyms ("lorry" vs "truck") are not
matched — treat the numbers as a relative signal between models, not an absolute accuracy.
"""

import re

from pydantic import BaseModel

_WORD = re.compile(r"[a-z]+")

# Function words carry no scene content; keeping them would let any fluent sentence score well.
_STOPWORDS = frozenset(
    """
    a an the and or but of in on at to from by with without for as is are was were be been being
    it its this that these those there here some any very just also into onto over under up down
    out off than then so while which who whom whose what where when how can could may might will
    would should has have had do does did not no
    """.split()  # noqa: SIM905 — a word list reads better than a quoted-literal list
)


class Score(BaseModel):
    precision: float
    recall: float
    f1: float
    word_count: int


def normalize_word(word: str) -> str | None:
    """Lowercase and lightly de-pluralise `word`; None for stopwords and non-words."""
    word = word.lower()
    if not _WORD.fullmatch(word) or word in _STOPWORDS:
        return None
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


def content_words(text: str) -> set[str]:
    return {w for raw in _WORD.findall(text.lower()) if (w := normalize_word(raw)) is not None}


def score(description: str, reference: str) -> Score:
    """Score `description` against `reference`. Raises if the reference has no content words."""
    ref_words = content_words(reference)
    if not ref_words:
        raise ValueError(f"reference {reference!r} has no content words to score against")
    words = content_words(description)
    overlap = len(words & ref_words)
    precision = overlap / len(words) if words else 0.0
    recall = overlap / len(ref_words)
    f1 = 2 * precision * recall / (precision + recall) if overlap else 0.0
    return Score(precision=precision, recall=recall, f1=f1, word_count=len(description.split()))
