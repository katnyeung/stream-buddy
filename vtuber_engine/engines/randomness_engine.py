"""
Randomness Engine - Generates spontaneous micro-actions.

Adds life to the avatar through occasional spontaneous gestures
like glances, small head movements, and expression changes.
Supports mood-aware action triggering for more expressive behavior.
"""
import random
from typing import Dict, List, Optional
from dataclasses import dataclass, field

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
    moods: Optional[List[str]] = None  # If set, only trigger in these moods (None = all moods)


# Base spontaneous actions (apply in any mood)
# Reduced weights and increased cooldowns for calmer idle behavior
SPONTANEOUS_ACTIONS: List[SpontaneousAction] = [
    # Eye movements - less frequent (reduced weights, increased cooldowns)
    SpontaneousAction("glance_left", "glance_left", 1.0, 8.0, [AvatarState.IDLE, AvatarState.LISTENING]),  # weight 2.0->1.0, cooldown 3.0->8.0
    SpontaneousAction("glance_right", "glance_right", 1.0, 8.0, [AvatarState.IDLE, AvatarState.LISTENING]),  # weight 2.0->1.0, cooldown 3.0->8.0

    # Head tilts - less frequent
    SpontaneousAction("tilt", "tilt", 0.5, 15.0, [AvatarState.IDLE, AvatarState.LISTENING, AvatarState.THINKING]),  # weight 1.0->0.5, cooldown 8.0->15.0

    # Brow movements - less frequent
    SpontaneousAction("raise_brow", "raise_brow_right", 0.3, 18.0, [AvatarState.LISTENING, AvatarState.THINKING]),  # weight 0.5->0.3, cooldown 10.0->18.0

    # Idle sway - rare (significantly reduced)
    SpontaneousAction("idle_sway", "idle_sway", 0.1, 30.0, [AvatarState.IDLE]),  # weight 0.3->0.1, cooldown 15.0->30.0

    # Slow blink - less frequent
    SpontaneousAction("slow_blink", "blink_slow", 0.3, 20.0, [AvatarState.IDLE, AvatarState.THINKING]),  # weight 0.5->0.3, cooldown 12.0->20.0
]


# Mood-specific spontaneous actions
# These have higher weights when in specific moods
# Cooldowns increased for less reactive behavior, especially for body/hand movements
MOOD_SPONTANEOUS_ACTIONS: Dict[str, List[SpontaneousAction]] = {
    # Happy mood: bouncy, energetic movements (reduced weights, increased cooldowns)
    "happy": [
        SpontaneousAction("happy_bounce", "bounce", 1.0, 15.0, [AvatarState.IDLE, AvatarState.SPEAKING, AvatarState.LISTENING]),  # weight 3.0->1.0, cooldown 5.0->15.0
        SpontaneousAction("happy_shrug", "shrug", 0.8, 20.0, [AvatarState.IDLE, AvatarState.SPEAKING]),  # weight 2.0->0.8, cooldown 7.0->20.0
        SpontaneousAction("happy_nod", "nod", 1.5, 10.0, [AvatarState.IDLE, AvatarState.LISTENING]),  # weight 2.0->1.5, cooldown 6.0->10.0
        SpontaneousAction("happy_sway", "sway", 0.5, 20.0, [AvatarState.IDLE]),  # weight 1.5->0.5, cooldown 8.0->20.0
    ],

    # Excited mood: even more energetic (significantly reduced)
    "excited": [
        SpontaneousAction("excited_bounce", "bounce", 1.5, 12.0, [AvatarState.IDLE, AvatarState.SPEAKING]),  # weight 4.0->1.5, cooldown 3.0->12.0
        SpontaneousAction("excited_hands", "excited_hands", 0.5, 25.0, [AvatarState.IDLE, AvatarState.SPEAKING]),  # weight 2.0->0.5, cooldown 8.0->25.0
        SpontaneousAction("excited_nod_fast", "nod_fast", 1.5, 8.0, [AvatarState.IDLE, AvatarState.LISTENING]),  # weight 2.5->1.5, cooldown 4.0->8.0
    ],

    # Thinking mood: contemplative, looking away, eye movements
    "thinking": [
        SpontaneousAction("thinking_look_away", "look_away", 3.5, 4.0, [AvatarState.IDLE, AvatarState.THINKING]),
        SpontaneousAction("thinking_eye_roll", "eye_roll", 2.0, 6.0, [AvatarState.IDLE, AvatarState.THINKING]),
        SpontaneousAction("thinking_look_up", "look_up", 2.5, 5.0, [AvatarState.IDLE, AvatarState.THINKING]),
        SpontaneousAction("thinking_ponder", "ponder", 1.5, 10.0, [AvatarState.IDLE, AvatarState.THINKING]),
        SpontaneousAction("thinking_tilt", "tilt_curious", 1.5, 8.0, [AvatarState.IDLE, AvatarState.THINKING]),
    ],

    # Curious mood: raised brows, tilts, wide eyes
    "curious": [
        SpontaneousAction("curious_raise_brows", "raise_brows", 3.5, 4.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("curious_tilt", "tilt_curious", 3.0, 5.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("curious_lean_in", "lean_in", 2.0, 8.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("curious_raise_brow_left", "raise_brow_left", 2.0, 6.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    ],

    # Surprised mood: wide-eyed, startled movements
    "surprised": [
        SpontaneousAction("surprised_raise_brows", "raise_brows", 4.0, 3.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("surprised_gasp", "gasp", 1.5, 10.0, [AvatarState.IDLE]),
        SpontaneousAction("surprised_lean_back", "lean_back", 2.0, 6.0, [AvatarState.IDLE]),
    ],

    # Sad mood: downcast, sighing
    "sad": [
        SpontaneousAction("sad_sigh", "sigh", 2.5, 6.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("sad_look_down", "look_down", 3.0, 5.0, [AvatarState.IDLE]),
        SpontaneousAction("sad_slow_blink", "blink_slow", 2.0, 4.0, [AvatarState.IDLE]),
    ],

    # Skeptical mood: raised brow, looking away
    "skeptical": [
        SpontaneousAction("skeptical_raise_brow", "raise_brow_right", 3.5, 4.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("skeptical_look_away", "look_away", 2.5, 5.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("skeptical_tilt", "tilt_right", 2.0, 6.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    ],

    # Annoyed mood: eye rolls, sighs
    "annoyed": [
        SpontaneousAction("annoyed_eye_roll", "eye_roll", 3.0, 5.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("annoyed_sigh", "sigh", 2.5, 6.0, [AvatarState.IDLE]),
        SpontaneousAction("annoyed_look_away", "look_away", 2.0, 5.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("annoyed_furrow", "furrow_brows", 2.0, 6.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    ],

    # Amused mood: light laughs, smirky movements
    "amused": [
        SpontaneousAction("amused_laugh", "laugh", 2.5, 6.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("amused_tilt", "tilt", 2.0, 5.0, [AvatarState.IDLE]),
        SpontaneousAction("amused_raise_brow", "raise_brow_right", 2.0, 5.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    ],

    # Confident mood: strong posture, decisive movements
    "confident": [
        SpontaneousAction("confident_nod", "nod", 2.5, 5.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("confident_lean_back", "lean_back", 1.5, 8.0, [AvatarState.IDLE]),
        SpontaneousAction("confident_sway", "sway", 1.5, 8.0, [AvatarState.IDLE]),
    ],

    # Concerned mood: worried expressions
    "concerned": [
        SpontaneousAction("concerned_furrow", "furrow_brows", 3.0, 4.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("concerned_tilt", "tilt", 2.0, 6.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("concerned_lean_in", "lean_in", 2.0, 7.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    ],

    # Shy mood: looking away, small movements
    "shy": [
        SpontaneousAction("shy_look_away", "look_away", 4.0, 4.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("shy_glance_left", "glance_left", 3.0, 3.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("shy_look_down", "look_down", 2.5, 5.0, [AvatarState.IDLE]),
    ],

    # Embarrassed mood: avoiding eye contact
    "embarrassed": [
        SpontaneousAction("embarrassed_look_away", "look_away", 4.0, 3.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("embarrassed_look_down", "look_down", 3.0, 4.0, [AvatarState.IDLE]),
        SpontaneousAction("embarrassed_slow_blink", "blink_slow", 2.0, 5.0, [AvatarState.IDLE]),
    ],

    # Mischievous mood: winks, playful movements
    "mischievous": [
        SpontaneousAction("mischievous_wink", "wink", 2.5, 6.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("mischievous_tilt", "tilt", 2.0, 5.0, [AvatarState.IDLE]),
        SpontaneousAction("mischievous_raise_brow", "raise_brow_right", 2.5, 5.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("mischievous_glance", "glance_right", 2.0, 4.0, [AvatarState.IDLE]),
    ],

    # Sleepy mood: slow blinks, droopy movements
    "sleepy": [
        SpontaneousAction("sleepy_slow_blink", "blink_slow", 4.0, 3.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("sleepy_look_down", "look_down", 2.5, 5.0, [AvatarState.IDLE]),
        SpontaneousAction("sleepy_sigh", "sigh", 1.5, 8.0, [AvatarState.IDLE]),
    ],

    # Friendly mood: warm, welcoming
    "friendly": [
        SpontaneousAction("friendly_nod", "nod", 2.5, 5.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("friendly_tilt", "tilt", 2.0, 6.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("friendly_lean_in", "lean_in", 1.5, 8.0, [AvatarState.LISTENING]),
    ],

    # Serious mood: minimal but deliberate movements
    "serious": [
        SpontaneousAction("serious_nod_slow", "nod_slow", 2.0, 8.0, [AvatarState.IDLE, AvatarState.LISTENING]),
        SpontaneousAction("serious_furrow", "furrow_brows", 1.5, 10.0, [AvatarState.IDLE, AvatarState.LISTENING]),
    ],

    # Determined mood: focused movements
    "determined": [
        SpontaneousAction("determined_nod", "nod", 2.0, 6.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("determined_lean_in", "lean_in", 1.5, 8.0, [AvatarState.IDLE]),
    ],

    # Proud mood: confident posture
    "proud": [
        SpontaneousAction("proud_nod", "nod", 2.5, 5.0, [AvatarState.IDLE, AvatarState.SPEAKING]),
        SpontaneousAction("proud_lean_back", "lean_back", 2.0, 7.0, [AvatarState.IDLE]),
        SpontaneousAction("proud_raise_brows", "raise_brows", 1.5, 8.0, [AvatarState.IDLE]),
    ],
}


class RandomnessEngine(BaseEngine):
    """
    Engine for spontaneous micro-actions.
    Triggers occasional gestures to make the avatar feel alive.
    Supports mood-aware action triggering for more expressive behavior.
    """

    def __init__(self):
        super().__init__(name="randomness")

        # Cooldowns for each action type (base actions)
        self._cooldowns: Dict[str, float] = {a.name: 0.0 for a in SPONTANEOUS_ACTIONS}

        # Add cooldowns for all mood-specific actions
        for mood_actions in MOOD_SPONTANEOUS_ACTIONS.values():
            for action in mood_actions:
                self._cooldowns[action.name] = 0.0

        # Global cooldown between any spontaneous action (increased for less reactivity)
        self._global_cooldown = 0.0
        self._min_global_cooldown = 4.0  # Increased from 2.0

        # Pending action to be executed by ActionEngine
        self._pending_action: Optional[str] = None

        # Mood action weight multiplier (reduced for less aggressive mood actions)
        self.mood_action_weight_multiplier = 1.0  # Reduced from 1.5

        # Hand gesture dampening - these gestures trigger less often
        self._hand_gesture_names = {
            "bounce", "shrug", "sway", "excited_hands", "wave", "clap",
            "hands_up", "thumbs_up", "present", "present_both", "wave_small",
            "facepalm", "hand_on_chest", "think_hand", "make_point", "emphasize",
            "welcome", "question_hand", "calm_down", "acknowledge_hand"
        }
        self._hand_gesture_weight_multiplier = 0.3  # Reduce hand gesture frequency

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

        # Check for spontaneous action trigger (now mood-aware)
        action = self._check_spontaneous_action(state, mood, personality)

        params = {}
        if action:
            self._pending_action = action.gesture
            params["_trigger_gesture"] = action.gesture

            # Set cooldowns
            self._cooldowns[action.name] = action.cooldown
            self._global_cooldown = personality.spontaneous_action_cooldown

        return params

    def _get_actions_for_mood(
        self,
        state: AvatarState,
        mood: str
    ) -> List[SpontaneousAction]:
        """
        Get all valid actions for current state and mood.
        Combines base actions with mood-specific ones.
        """
        valid_actions = []

        # Add base spontaneous actions that are valid for this state
        for action in SPONTANEOUS_ACTIONS:
            if state in action.states and self._cooldowns.get(action.name, 0) <= 0:
                # Check if action has mood restriction
                if action.moods is None or mood.lower() in [m.lower() for m in action.moods]:
                    valid_actions.append(action)

        # Add mood-specific actions if in that mood
        mood_lower = mood.lower()
        if mood_lower in MOOD_SPONTANEOUS_ACTIONS:
            for action in MOOD_SPONTANEOUS_ACTIONS[mood_lower]:
                if state in action.states and self._cooldowns.get(action.name, 0) <= 0:
                    valid_actions.append(action)

        return valid_actions

    def _check_spontaneous_action(
        self,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile
    ) -> Optional[SpontaneousAction]:
        """
        Check if a spontaneous action should trigger.
        Uses weighted random selection with mood awareness.
        """
        # Get actions valid for current state and mood
        valid_actions = self._get_actions_for_mood(state, mood)

        if not valid_actions:
            return None

        # Calculate total weight (mood-specific actions get bonus weight)
        mood_lower = mood.lower()
        mood_action_names = set()
        if mood_lower in MOOD_SPONTANEOUS_ACTIONS:
            mood_action_names = {a.name for a in MOOD_SPONTANEOUS_ACTIONS[mood_lower]}

        weighted_actions = []
        total_weight = 0.0
        for action in valid_actions:
            # Boost weight for mood-specific actions
            weight = action.weight
            if action.name in mood_action_names:
                weight *= self.mood_action_weight_multiplier

            # Reduce weight for hand gestures to make them less reactive
            if action.gesture in self._hand_gesture_names:
                weight *= self._hand_gesture_weight_multiplier

            weighted_actions.append((action, weight))
            total_weight += weight

        # Base chance modified by personality
        chance = personality.spontaneous_action_chance

        # Roll for action
        if random.random() > chance:
            return None

        # Weighted random selection
        roll = random.random() * total_weight
        cumulative = 0.0

        for action, weight in weighted_actions:
            cumulative += weight
            if roll <= cumulative:
                return action

        return weighted_actions[-1][0] if weighted_actions else None

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
        # Reset base action cooldowns
        self._cooldowns = {a.name: 0.0 for a in SPONTANEOUS_ACTIONS}
        # Reset mood-specific action cooldowns
        for mood_actions in MOOD_SPONTANEOUS_ACTIONS.values():
            for action in mood_actions:
                self._cooldowns[action.name] = 0.0
        self._global_cooldown = 0.0
        self._pending_action = None
