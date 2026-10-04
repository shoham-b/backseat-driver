"""Lexical scoring of a model description against nuScenes' human-written scene label.

nuScenes labels are terse keyword lists ("Parked truck, construction, intersection, turn left"),
so we score *content-word overlap*, not fluency. Precision punishes padding, recall rewards
covering what the label mentions, F1 balances them. Synonyms ("lorry" vs "truck") are not
matched — treat the numbers as a relative signal between models, not an absolute accuracy.
"""

import re
from functools import cache

import snowballstemmer
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

# Boilerplate a VLM wraps around a caption ("The image shows ...") that no nuScenes label contains;
# left in, it would count against precision for models that happen to phrase captions that way.
_BOILERPLATE = frozenset(
    """
    image picture photo photograph shot view scene
    show shows showing shown depict depicts depicting depicted display displays displaying
    appear appears appearing seem seems look looks looking see sees seen visible
    """.split()  # noqa: SIM905
)


class Score(BaseModel):
    precision: float
    recall: float
    f1: float
    word_count: int


def normalize_word(word: str) -> str | None:
    """Lowercase and stem `word`; None for stopwords, boilerplate and non-words."""
    word = word.lower()
    if not _WORD.fullmatch(word) or word in _STOPWORDS or word in _BOILERPLATE:
        return None
    return _stem(word)


# Porter2 leaves "buses" as "buse", which never meets "bus"; buses and people are common in driving scenes.
_IRREGULAR = {"buses": "bus", "people": "person"}


@cache
def _stem(word: str) -> str:
    """Fold inflections ("parked", "turning", "lorries") onto one stem.

    A stemmer per call because Snowball stemmers keep scratch state and the UI scores on a thread pool; the cache
    makes that one construction per distinct word.
    """
    word = _IRREGULAR.get(word, word)
    return snowballstemmer.stemmer("english").stemWord(word)


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
