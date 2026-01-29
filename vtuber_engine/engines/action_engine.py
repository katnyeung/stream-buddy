"""
Action Engine - Executes moods and gestures with timing and interpolation.

Handles:
- Mood transitions (persistent expressions)
- Gesture animations (one-shot keyframe animations)
- Action queue processing
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .base_engine import BaseEngine
from ..models.state import AvatarState
from ..models.personality import PersonalityProfile
from ..models.actions import (
    MoodDefinition,
    GestureDefinition,
    GestureKeyframe,
    MOODS,
    GESTURES,
    GESTURE_ALIASES,
    COMPOUND_ACTIONS,
    get_mood,
    get_gesture,
    resolve_alias,
)
from ..utils.easing import ease_out_cubic, ease_in_out_quad, lerp


def quantize_intensity(intensity: float) -> float:
    """
    Quantize intensity to standard values: 0.0, 0.5, or 1.0.
    This provides more predictable gesture behavior.

    Args:
        intensity: Raw intensity value (0.0-1.0)

    Returns:
        Quantized intensity (0.0, 0.5, or 1.0)
    """
    if intensity is None:
        return 1.0
    if intensity <= 0.25:
        return 0.0
    elif intensity <= 0.75:
        return 0.5
    else:
        return 1.0


@dataclass
class ActiveGesture:
    """A gesture currently being animated."""
    name: str
    definition: GestureDefinition
    start_time: float
    intensity: float = 1.0
    current_values: Dict[str, float] = field(default_factory=dict)

    @property
    def duration_sec(self) -> float:
        return self.definition.duration_ms / 1000.0


@dataclass
class MoodTransition:
    """An active mood transition."""
    from_params: Dict[str, float]
    to_params: Dict[str, float]
    duration_sec: float
    start_time: float
    mood_name: str


class ActionEngine(BaseEngine):
    """
    Engine for executing moods and gestures.
    Ported from JavaScript ActionExecutor.
    """

    def __init__(self):
        super().__init__(name="action")

        # Current mood state
        self._current_mood: Optional[MoodDefinition] = None
        self._current_mood_name: str = "neutral"
        self._mood_params: Dict[str, float] = {}

        # Mood transition state
        self._mood_transition: Optional[MoodTransition] = None

        # Active gestures (can have multiple)
        self._active_gestures: List[ActiveGesture] = []

        # Action queue
        self._action_queue: List[Dict[str, Any]] = []

        # Global intensity multiplier
        self.global_intensity = 1.0

        # Parameters to exclude from action control (e.g., mouthOpen for lipsync)
        self._excluded_params: set = set()

        # Initialize with neutral mood
        self._init_neutral_mood()

    def _init_neutral_mood(self) -> None:
        """Initialize with neutral mood parameters."""
        neutral = get_mood("neutral")
        if neutral:
            self._current_mood = neutral
            self._current_mood_name = "neutral"
            self._mood_params = neutral.params.copy()

    def update(
        self,
        delta_time: float,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile,
        current_params: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Update mood transitions and gesture animations.
        Returns combined parameter modifications.
        """
        if not self.enabled:
            return {}

        self.tick(delta_time)

        # Process queued actions
        self._process_queue()

        # Update mood transition
        self._update_mood_transition()

        # Update active gestures
        self._update_gestures()

        # Calculate final parameters
        return self._calculate_output()

    def _process_queue(self) -> None:
        """Process the next action from the queue."""
        if not self._action_queue:
            return

        # Get next action
        action = self._action_queue.pop(0)
        action_type = action.get("type", "")
        name = action.get("name", "")
        params = action.get("params", {})

        if action_type == "mood":
            self.set_mood(name, params.get("intensity"), params.get("duration"))
        elif action_type == "gesture":
            self.play_gesture(name, params.get("intensity"), params.get("duration"))
        elif action_type == "action":
            self.execute_compound(name, params.get("intensity"))
        elif action_type in ("eye", "head", "body", "brow"):
            # Resolve alias to gesture
            gesture_name = resolve_alias(action_type, name)
            if gesture_name:
                self.play_gesture(gesture_name, params.get("intensity"), params.get("duration"))

    def _update_mood_transition(self) -> None:
        """Update active mood transition interpolation."""
        if not self._mood_transition:
            return

        elapsed = self._time - self._mood_transition.start_time
        progress = min(1.0, elapsed / self._mood_transition.duration_sec)

        # Ease the transition
        eased = ease_out_cubic(progress)

        # Interpolate parameters
        for key, target_val in self._mood_transition.to_params.items():
            start_val = self._mood_transition.from_params.get(key, 0)
            self._mood_params[key] = lerp(start_val, target_val, eased)

        # Complete transition
        if progress >= 1.0:
            self._mood_params = self._mood_transition.to_params.copy()
            self._mood_transition = None

    def _update_gestures(self) -> None:
        """Update all active gesture animations."""
        completed = []

        for gesture in self._active_gestures:
            elapsed = self._time - gesture.start_time
            progress = min(1.0, elapsed / gesture.duration_sec)

            if progress >= 1.0:
                # Gesture complete
                completed.append(gesture)
                gesture.current_values = {}
            else:
                # Interpolate keyframes
                gesture.current_values = self._interpolate_keyframes(
                    gesture.definition.keyframes,
                    progress,
                    gesture.intensity
                )

        # Remove completed gestures
        for gesture in completed:
            self._active_gestures.remove(gesture)

    def _interpolate_keyframes(
        self,
        keyframes: List[GestureKeyframe],
        progress: float,
        intensity: float
    ) -> Dict[str, float]:
        """
        Interpolate keyframe values at given progress.
        """
        if not keyframes:
            return {}

        # Find surrounding keyframes
        prev_frame = keyframes[0]
        next_frame = keyframes[-1]

        for i in range(len(keyframes) - 1):
            if keyframes[i].t <= progress <= keyframes[i + 1].t:
                prev_frame = keyframes[i]
                next_frame = keyframes[i + 1]
                break

        # Calculate local progress between frames
        frame_range = next_frame.t - prev_frame.t
        if frame_range > 0:
            local_progress = (progress - prev_frame.t) / frame_range
        else:
            local_progress = 0

        # Ease the local progress
        eased = ease_in_out_quad(local_progress)

        # Interpolate all parameters
        all_params = set()
        for kf in keyframes:
            all_params.update(kf.params.keys())

        result = {}
        for param in all_params:
            prev_val = prev_frame.params.get(param, 0)
            next_val = next_frame.params.get(param, 0)
            result[param] = lerp(prev_val, next_val, eased) * intensity

        return result

    def _calculate_output(self) -> Dict[str, float]:
        """Calculate final output parameters from mood + gestures."""
        # Start with mood params
        final_params = self._mood_params.copy()

        # Add gesture offsets
        for gesture in self._active_gestures:
            for key, value in gesture.current_values.items():
                if gesture.definition.relative:
                    # Relative: add to mood value
                    final_params[key] = final_params.get(key, 0) + value
                else:
                    # Absolute: override mood value
                    final_params[key] = value

        # Remove excluded params
        for param in self._excluded_params:
            final_params.pop(param, None)

        return final_params

    # === Public API ===

    def set_mood(
        self,
        mood_name: str,
        intensity: Optional[float] = None,
        duration_ms: Optional[int] = None
    ) -> bool:
        """
        Set a new mood with smooth transition.

        Args:
            mood_name: Name of the mood
            intensity: Blend intensity (0-1), quantized to 0.0, 0.5, or 1.0
            duration_ms: Transition duration, default from mood definition

        Returns:
            True if mood was found and set
        """
        mood = get_mood(mood_name)
        if not mood:
            return False

        # Quantize intensity to standard values (0.0, 0.5, 1.0)
        intensity = quantize_intensity(intensity) * self.global_intensity
        duration_sec = (duration_ms or mood.transition_ms) / 1000.0

        # Calculate target params with intensity
        neutral = get_mood("neutral")
        neutral_params = neutral.params if neutral else {}

        target_params = {}
        for key, value in mood.params.items():
            neutral_val = neutral_params.get(key, 0)
            target_params[key] = neutral_val + (value - neutral_val) * intensity

        # Start transition
        self._mood_transition = MoodTransition(
            from_params=self._mood_params.copy(),
            to_params=target_params,
            duration_sec=duration_sec,
            start_time=self._time,
            mood_name=mood_name
        )

        self._current_mood = mood
        self._current_mood_name = mood_name

        return True

    def play_gesture(
        self,
        gesture_name: str,
        intensity: Optional[float] = None,
        duration_ms: Optional[int] = None
    ) -> bool:
        """
        Play a one-shot gesture animation.

        Args:
            gesture_name: Name of the gesture
            intensity: Animation intensity, quantized to 0.0, 0.5, or 1.0
            duration_ms: Override duration, default from gesture definition

        Returns:
            True if gesture was found and started
        """
        gesture = get_gesture(gesture_name)
        if not gesture:
            return False

        # Quantize intensity to standard values (0.0, 0.5, 1.0)
        intensity = quantize_intensity(intensity) * self.global_intensity

        # Create gesture with potentially overridden duration
        definition = gesture
        if duration_ms:
            # Create a modified definition with new duration
            definition = GestureDefinition(
                name=gesture.name,
                keyframes=gesture.keyframes,
                duration_ms=duration_ms,
                relative=gesture.relative
            )

        active = ActiveGesture(
            name=gesture_name,
            definition=definition,
            start_time=self._time,
            intensity=intensity
        )

        self._active_gestures.append(active)
        return True

    def execute_compound(
        self,
        action_name: str,
        intensity: Optional[float] = None
    ) -> bool:
        """
        Execute a compound action (mood + gesture).

        Args:
            action_name: Name of the compound action
            intensity: Intensity for both mood and gesture (quantized to 0.0, 0.5, 1.0)

        Returns:
            True if action was found and executed
        """
        action = COMPOUND_ACTIONS.get(action_name.lower())
        if not action:
            return False

        # Quantize intensity once for both mood and gesture
        quantized = quantize_intensity(intensity)

        success = True
        if action.get("mood"):
            success = self.set_mood(action["mood"], quantized) and success
        if action.get("gesture"):
            success = self.play_gesture(action["gesture"], quantized) and success

        return success

    def queue_action(
        self,
        action_type: str,
        name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an action to the queue for processing."""
        self._action_queue.append({
            "type": action_type,
            "name": name,
            "params": params or {}
        })

    def exclude_param(self, param_name: str) -> None:
        """Exclude a parameter from action control (e.g., for lip sync)."""
        self._excluded_params.add(param_name)

    def include_param(self, param_name: str) -> None:
        """Re-include a parameter."""
        self._excluded_params.discard(param_name)

    def clear_mood(self) -> None:
        """Clear current mood and transition."""
        self._current_mood = None
        self._current_mood_name = ""
        self._mood_params = {}
        self._mood_transition = None

    def clear_gestures(self) -> None:
        """Clear all active gestures."""
        self._active_gestures = []

    def clear_queue(self) -> None:
        """Clear the action queue."""
        self._action_queue = []

    def reset(self) -> None:
        """Reset to initial state."""
        super().reset()
        self._init_neutral_mood()
        self._active_gestures = []
        self._action_queue = []
        self._mood_transition = None

    # === Properties ===

    @property
    def current_mood_name(self) -> str:
        return self._current_mood_name

    @property
    def active_gesture_count(self) -> int:
        return len(self._active_gestures)

    @property
    def active_gesture_names(self) -> List[str]:
        return [g.name for g in self._active_gestures]

    @property
    def is_transitioning(self) -> bool:
        return self._mood_transition is not None

    @property
    def queue_length(self) -> int:
        return len(self._action_queue)
