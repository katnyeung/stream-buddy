"""
State Engine - Generates state-specific behaviors.

Different behaviors for each avatar state:
- idle: Relaxed, default movement
- listening: Attentive, occasional nods
- speaking: Expressive, more head movement
- thinking: Contemplative, looking away
"""
import random
from typing import Dict, Optional

from .base_engine import BaseEngine
from ..models.state import AvatarState, get_state_config, StateConfig
from ..models.personality import PersonalityProfile
from ..utils.easing import ease_out_cubic, lerp


class StateEngine(BaseEngine):
    """
    Engine for state-specific behaviors.
    Modifies movement based on current avatar state.
    """

    def __init__(self):
        super().__init__(name="state")

        # State transition
        self._current_state: Optional[AvatarState] = None
        self._previous_state: Optional[AvatarState] = None
        self._transition_progress = 1.0  # 1.0 = complete
        self._transition_duration = 0.5  # Seconds

        # State-specific timers
        self._nod_cooldown = 0.0
        self._look_away_cooldown = 0.0
        self._state_action_cooldown = 0.0

        # Current state params being transitioned to
        self._target_params: Dict[str, float] = {}
        self._start_params: Dict[str, float] = {}

    def update(
        self,
        delta_time: float,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile,
        current_params: Dict[str, float],
    ) -> Dict[str, float]:
        """Generate state-specific parameter modifications."""
        if not self.enabled:
            return {}

        self.tick(delta_time)

        # Check for state change
        if state != self._current_state:
            self._on_state_change(state, current_params)

        # Update transition
        params = self._update_transition(delta_time)

        # Add state-specific behaviors
        state_params = self._update_state_behaviors(delta_time, state, personality)
        params.update(state_params)

        # Update cooldowns
        self._nod_cooldown = max(0, self._nod_cooldown - delta_time)
        self._look_away_cooldown = max(0, self._look_away_cooldown - delta_time)
        self._state_action_cooldown = max(0, self._state_action_cooldown - delta_time)

        return params

    def _on_state_change(self, new_state: AvatarState, current_params: Dict[str, float]) -> None:
        """Handle state transition."""
        self._previous_state = self._current_state
        self._current_state = new_state
        self._transition_progress = 0.0

        # Get target params from new state config
        config = get_state_config(new_state)
        self._target_params = config.base_params.copy()

        # Store current params as start
        self._start_params = {k: current_params.get(k, 0) for k in self._target_params}

    def _update_transition(self, delta_time: float) -> Dict[str, float]:
        """Update state transition interpolation."""
        if self._transition_progress >= 1.0:
            return self._target_params.copy()

        # Update progress
        self._transition_progress += delta_time / self._transition_duration
        self._transition_progress = min(1.0, self._transition_progress)

        # Ease the progress
        eased = ease_out_cubic(self._transition_progress)

        # Interpolate parameters
        params = {}
        for key, target_val in self._target_params.items():
            start_val = self._start_params.get(key, 0)
            params[key] = lerp(start_val, target_val, eased)

        return params

    def _update_state_behaviors(
        self,
        delta_time: float,
        state: AvatarState,
        personality: PersonalityProfile
    ) -> Dict[str, float]:
        """Generate state-specific behaviors like nods and glances."""
        config = get_state_config(state)
        params = {}

        if state == AvatarState.LISTENING:
            params.update(self._listening_behavior(personality, config))

        elif state == AvatarState.SPEAKING:
            params.update(self._speaking_behavior(personality, config))

        elif state == AvatarState.THINKING:
            params.update(self._thinking_behavior(personality, config))

        return params

    def _listening_behavior(
        self,
        personality: PersonalityProfile,
        config: StateConfig
    ) -> Dict[str, float]:
        """
        Listening state: occasional nods to show attention.
        Returns parameters for a small head tilt that indicates attention.
        """
        params = {}

        # Chance to trigger a nod
        nod_chance = config.nod_chance or personality.listening_nod_chance

        if self._nod_cooldown <= 0 and random.random() < nod_chance * 0.016:  # Per frame @ 60fps
            # This signals that a nod should be queued
            # The actual nod gesture is handled by ActionEngine
            params["_trigger_gesture"] = "nod"
            self._nod_cooldown = 3.0  # Cooldown before next nod

        return params

    def _speaking_behavior(
        self,
        personality: PersonalityProfile,
        config: StateConfig
    ) -> Dict[str, float]:
        """
        Speaking state: more expressive head movement.
        The actual movement is handled by idle engine, but we increase scale here.
        """
        return {
            "_head_movement_scale": config.head_movement_scale,
            "_body_movement_scale": config.body_movement_scale,
        }

    def _thinking_behavior(
        self,
        personality: PersonalityProfile,
        config: StateConfig
    ) -> Dict[str, float]:
        """
        Thinking state: contemplative look-away behavior.
        """
        params = {}

        look_away_chance = config.look_away_chance or personality.thinking_look_away_chance

        if self._look_away_cooldown <= 0 and random.random() < look_away_chance * 0.008:
            params["_trigger_gesture"] = "look_away"
            self._look_away_cooldown = 5.0

        return params

    def get_movement_scales(self) -> Dict[str, float]:
        """Get current movement scale multipliers based on state."""
        if self._current_state:
            config = get_state_config(self._current_state)
            return {
                "head": config.head_movement_scale,
                "body": config.body_movement_scale,
            }
        return {"head": 1.0, "body": 1.0}

    def reset(self) -> None:
        """Reset engine state."""
        super().reset()
        self._current_state = None
        self._previous_state = None
        self._transition_progress = 1.0
        self._nod_cooldown = 0.0
        self._look_away_cooldown = 0.0
