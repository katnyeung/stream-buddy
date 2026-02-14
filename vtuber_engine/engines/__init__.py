"""
VTuber Engines - Animation engines that generate parameter updates.

Each engine is responsible for a specific aspect of avatar animation:
- IdleEngine: Breathing, noise, blinks
- StateEngine: State-specific behaviors
- ActionEngine: Mood/gesture execution
- LipSyncEngine: Audio amplitude processing
- RandomnessEngine: Spontaneous actions
"""

from .base_engine import BaseEngine
from .idle_engine import IdleEngine
from .state_engine import StateEngine
from .lipsync_engine import LipSyncEngine
from .randomness_engine import RandomnessEngine
from .action_engine import ActionEngine

__all__ = [
    "BaseEngine",
    "IdleEngine",
    "StateEngine",
    "LipSyncEngine",
    "RandomnessEngine",
    "ActionEngine",
]
