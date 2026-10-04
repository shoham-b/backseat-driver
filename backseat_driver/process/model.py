"""The specific vision-language model a backend runs.

Kept apart from `CaptionBackend` (where inference happens) because the two vary
independently: the same model can be served by different backends, and one backend
serves many models.
"""

from dataclasses import dataclass

# Prompt shared by the prompt-capable models so their output is comparable.
SCENE_PROMPT = (
    "Describe this driving scene from the vehicle's front camera in one short sentence of at most "
    "20 words. Mention only the most important elements: road, traffic or pedestrians, weather."
)


@dataclass(frozen=True)
class CaptionModel:
    """A model to caption with, and how to ask it.

    `prompt` is ignored by backends whose models cannot take one (a HuggingFace
    `image-to-text` pipeline such as BLIP captions unconditionally).
    """

    name: str
    prompt: str = SCENE_PROMPT
