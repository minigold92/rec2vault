"""Default pipeline: audio, models, text, then note publication.

Adapters own stage parameters; execution state and cache policy stay in executor.
"""
from . import audio, models, note, text


def default_registry():
    return (*audio.stages(), *models.stages(), *text.stages(), *note.stages())
