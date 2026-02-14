"""
Base Engine - Abstract base class for all animation engines.

Each engine implements the update() method which returns parameter
modifications based on the current state, mood, and time.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional

from ..models.state import AvatarState
from ..models.personality import PersonalityProfile


class BaseEngine(ABC):
    """
    Abstract base class for animation engines.

    Each engine receives state information and returns parameter deltas
    to be blended by the ParameterBlender.
    """

    def __init__(self, name: str = "base"):
        """
        Initialize the engine.

        Args:
            name: Engine name for logging
        """
        self.name = name
        self.enabled = True
        self.weight = 1.0  # Blend weight (0-1)
        self._time = 0.0   # Accumulated time

    @abstractmethod
    def update(
        self,
        delta_time: float,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile,
        current_params: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Update the engine and return parameter modifications.

        Args:
            delta_time: Time since last update (seconds)
            state: Current avatar state
            mood: Current mood name
            personality: Current personality profile
            current_params: Current parameter values

        Returns:
            Dict of parameter modifications (may be relative or absolute
            depending on the engine)
        """
        pass

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self._time = 0.0

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the engine."""
        self.enabled = enabled

    def set_weight(self, weight: float) -> None:
        """Set the blend weight (0-1)."""
        self.weight = max(0.0, min(1.0, weight))

    def tick(self, delta_time: float) -> None:
        """Update internal time."""
        self._time += delta_time

    @property
    def time(self) -> float:
        """Get accumulated time."""
        return self._time
