"""The specific vision-language model a backend runs.

Kept apart from `CaptionBackend` (where inference happens) because the two vary
independently: the same model can be served by different backends, and one backend
serves many models.
"""

from dataclasses import dataclass

# Prompt shared by the prompt-capable models so their output is comparable. nuScenes' scene labels are terse
# keyword lists, which the report scores by word overlap, so asking for the same shape keeps models from being
# judged on phrasing. The example is invented: a label from an evaluated scene would leak into the scores.
SCENE_PROMPT = (
    "List the key elements of this driving scene from the vehicle's front camera as a short, "
    "comma-separated list of keywords, like 'Wet road, cyclist crossing, bus ahead, stopped at traffic light'. "
    "Cover the road, traffic or pedestrians, weather or lighting, and what the vehicle is doing. "
    "Use no sentences and no more than eight items."
)


@dataclass(frozen=True)
class CaptionModel:
    """A model to caption with, and how to ask it.

    `prompt` is ignored by backends whose models cannot take one (a HuggingFace
    `image-to-text` pipeline such as BLIP captions unconditionally).
    """

    name: str
    prompt: str = SCENE_PROMPT
