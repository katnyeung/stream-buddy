"""
Randomness Engine - Generates spontaneous micro-actions.

Adds life to the avatar through occasional spontaneous gestures
like glances, small head movements, and expression changes.
"""
import random
from typing import Dict, List, Optional
from dataclasses import dataclass

from .base_engine import BaseEngine
from ..models.state import AvatarState
from ..models.personality import PersonalityProfile


@dataclass
class SpontaneousAction:
    """Definition of a spontaneous action."""
    name: str
    gesture: str  # Gesture name to trigger
    weight: float  # Relative probability
    cooldown: float  # Minimum seconds between occurrences
    states: List[AvatarState]  # States where this can occur


# Spontaneous actions that can occur
SPONTANEOUS_ACTIONS: List[SpontaneousAction] = [
    # Eye movements - frequent but subtle
    SpontaneousAction("glance_left", "glance_left", 2.0, 3.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    SpontaneousAction("glance_right", "glance_right", 2.0, 3.0, [AvatarState.IDLE, AvatarState.LISTENING]),

    # Head tilts - occasional
    SpontaneousAction("tilt", "tilt", 1.0, 8.0, [AvatarState.IDLE, AvatarState.LISTENING, AvatarState.THINKING]),

    # Brow movements - add expression
    SpontaneousAction("raise_brow", "raise_brow_right", 0.5, 10.0, [AvatarState.LISTENING, AvatarState.THINKING]),

    # Idle sway - very occasional
    SpontaneousAction("idle_sway", "idle_sway", 0.3, 15.0, [AvatarState.IDLE]),

    # Slow blink - occasional deliberate blink
    SpontaneousAction("slow_blink", "blink_slow", 0.5, 12.0, [AvatarState.IDLE, AvatarState.THINKING]),
]


class RandomnessEngine(BaseEngine):
    """
    Engine for spontaneous micro-actions.
    Triggers occasional gestures to make the avatar feel alive.
    """

    def __init__(self):
        super().__init__(name="randomness")

        # Cooldowns for each action type
        self._cooldowns: Dict[str, float] = {a.name: 0.0 for a in SPONTANEOUS_ACTIONS}

        # Global cooldown between any spontaneous action
        self._global_cooldown = 0.0
        self._min_global_cooldown = 2.0

        # Pending action to be executed by ActionEngine
        self._pending_action: Optional[str] = None

    def update(
        self,
        delta_time: float,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile,
        current_params: Dict[str, float],
    ) -> Dict[str, float]:
        """Check for and trigger spontaneous actions."""
        if not self.enabled:
            return {}

        self.tick(delta_time)

        # Update cooldowns
        self._global_cooldown = max(0, self._global_cooldown - delta_time)
        for name in self._cooldowns:
            self._cooldowns[name] = max(0, self._cooldowns[name] - delta_time)

        # Clear pending action
        self._pending_action = None

        # Skip if in global cooldown
        if self._global_cooldown > 0:
            return {}

        # Check for spontaneous action trigger
        action = self._check_spontaneous_action(state, personality)

        params = {}
        if action:
            self._pending_action = action.gesture
            params["_trigger_gesture"] = action.gesture

            # Set cooldowns
            self._cooldowns[action.name] = action.cooldown
            self._global_cooldown = personality.spontaneous_action_cooldown

        return params

    def _check_spontaneous_action(
        self,
        state: AvatarState,
        personality: PersonalityProfile
    ) -> Optional[SpontaneousAction]:
        """
        Check if a spontaneous action should trigger.
        Uses weighted random selection.
        """
        # Get actions valid for current state
        valid_actions = [
            a for a in SPONTANEOUS_ACTIONS
            if state in a.states and self._cooldowns.get(a.name, 0) <= 0
        ]

        if not valid_actions:
            return None

        # Calculate total weight
        total_weight = sum(a.weight for a in valid_actions)

        # Base chance modified by personality
        chance = personality.spontaneous_action_chance

        # Roll for action
        if random.random() > chance:
            return None

        # Weighted random selection
        roll = random.random() * total_weight
        cumulative = 0.0

        for action in valid_actions:
            cumulative += action.weight
            if roll <= cumulative:
                return action

        return valid_actions[-1] if valid_actions else None

    @property
    def pending_action(self) -> Optional[str]:
        """Get the pending spontaneous action gesture name."""
        return self._pending_action

    def clear_pending(self) -> None:
        """Clear the pending action after it's been processed."""
        self._pending_action = None

    def reset(self) -> None:
        """Reset engine state."""
        super().reset()
        self._cooldowns = {a.name: 0.0 for a in SPONTANEOUS_ACTIONS}
        self._global_cooldown = 0.0
        self._pending_action = None
