"""
VTuber Engine Models - Data models for avatar parameters, state, and actions.
"""

from .params import (
    AvatarParams,
    PARAM_DEFAULTS,
    PARAM_RANGES,
    clamp_params,
)
from .personality import (
    PersonalityProfile,
    PERSONALITY_PRESETS,
)
from .state import (
    AvatarState,
    STATE_TRANSITIONS,
)
from .actions import (
    MoodDefinition,
    GestureDefinition,
    MOODS,
    GESTURES,
    GESTURE_ALIASES,
)

__all__ = [
    "AvatarParams",
    "PARAM_DEFAULTS",
    "PARAM_RANGES",
    "clamp_params",
    "PersonalityProfile",
    "PERSONALITY_PRESETS",
    "AvatarState",
    "STATE_TRANSITIONS",
    "MoodDefinition",
    "GestureDefinition",
    "MOODS",
    "GESTURES",
    "GESTURE_ALIASES",
]
