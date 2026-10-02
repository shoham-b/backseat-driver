"""The specific vision-language model a backend runs.

Kept apart from `CaptionBackend` (where inference happens) because the two vary
independently: the same model can be served by different backends, and one backend
serves many models.
"""

from dataclasses import dataclass

# Prompt shared by the prompt-capable models so their output is comparable.
DETAILED_SCENE_PROMPT = (
    "Describe this driving scene from the vehicle's front camera in detail: the road layout, "
    "traffic and pedestrians, weather and lighting, and any hazards."
)


@dataclass(frozen=True)
class CaptionModel:
    """A model to caption with, and how to ask it.

    `prompt` is ignored by backends whose models cannot take one (a HuggingFace
    `image-to-text` pipeline such as BLIP captions unconditionally).
    """

    name: str
    prompt: str = DETAILED_SCENE_PROMPT
