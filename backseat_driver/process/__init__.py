"""Stage 2, process: caption a keyframe image with a vision-language model.

The `Captioner` port, built from a `CaptionBackend` (where inference runs) plus a `CaptionModel` (which model and
prompt). The monolith calls it in-process; the distributed caption worker calls the same class once per queue task.
"""
