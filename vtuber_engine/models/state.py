"""
Avatar state machine definitions.

States:
- idle: Default state, gentle ambient movement
- listening: User is speaking, attentive behavior
- speaking: Avatar is speaking (TTS playing), mouth moving
- thinking: Processing/waiting for response, contemplative behavior
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class AvatarState(str, Enum):
    """Avatar behavioral states."""
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    THINKING = "thinking"


@dataclass
class StateConfig:
    """Configuration for a specific state."""
    name: AvatarState
    description: str

    # Base expression modifiers (applied on state entry)
    base_params: Dict[str, float]

    # Behaviors enabled in this state
    enable_blink: bool = True
    enable_breathing: bool = True
    enable_noise: bool = True
    enable_lip_sync: bool = False

    # State-specific behavior settings
    head_movement_scale: float = 1.0
    body_movement_scale: float = 1.0

    # Spontaneous action probabilities (overrides personality)
    nod_chance: Optional[float] = None
    look_away_chance: Optional[float] = None
    tilt_chance: Optional[float] = None


# State configurations with their default behaviors
STATE_CONFIGS: Dict[AvatarState, StateConfig] = {
    AvatarState.IDLE: StateConfig(
        name=AvatarState.IDLE,
        description="Default relaxed state",
        base_params={
            "angleX": 0,
            "angleY": 0,
            "angleZ": 2,
            "mouthForm": 0,
        },
        enable_blink=True,
        enable_breathing=True,
        enable_noise=True,
        enable_lip_sync=False,
        head_movement_scale=1.0,
        body_movement_scale=1.0,
    ),

    AvatarState.LISTENING: StateConfig(
        name=AvatarState.LISTENING,
        description="Attentively listening to user",
        base_params={
            "angleX": 0,
            "angleY": -3,  # Slight lean forward
            "angleZ": 0,
            "eyeOpenL": 1.05,
            "eyeOpenR": 1.05,
            "browLY": 0.1,
            "browRY": 0.1,
        },
        enable_blink=True,
        enable_breathing=True,
        enable_noise=True,
        enable_lip_sync=False,
        head_movement_scale=0.8,  # Less random head movement
        body_movement_scale=0.6,
        nod_chance=0.15,  # Occasional nods while listening
        look_away_chance=0.05,
    ),

    AvatarState.SPEAKING: StateConfig(
        name=AvatarState.SPEAKING,
        description="Avatar is speaking (TTS playing)",
        base_params={
            "angleX": 0,
            "angleY": 0,
            "angleZ": 3,
            "mouthForm": 0.2,  # Slight smile while speaking
        },
        enable_blink=True,
        enable_breathing=True,
        enable_noise=True,
        enable_lip_sync=True,
        head_movement_scale=1.2,  # More expressive head movement
        body_movement_scale=1.0,
        nod_chance=0.08,
        tilt_chance=0.05,
    ),

    AvatarState.THINKING: StateConfig(
        name=AvatarState.THINKING,
        description="Processing, contemplative",
        base_params={
            "angleX": -5,  # Looking slightly to side
            "angleY": 5,   # Head slightly up
            "angleZ": 3,
            "eyeBallX": 0.3,
            "eyeBallY": -0.2,
            "browLY": -0.1,
            "browRY": 0.2,
            "mouthForm": 0.1,
        },
        enable_blink=True,
        enable_breathing=True,
        enable_noise=True,
        enable_lip_sync=False,
        head_movement_scale=0.5,
        body_movement_scale=0.4,
        look_away_chance=0.3,
        tilt_chance=0.1,
    ),
}


# Valid state transitions
STATE_TRANSITIONS: Dict[AvatarState, List[AvatarState]] = {
    AvatarState.IDLE: [AvatarState.LISTENING, AvatarState.SPEAKING, AvatarState.THINKING],
    AvatarState.LISTENING: [AvatarState.IDLE, AvatarState.SPEAKING, AvatarState.THINKING],
    AvatarState.SPEAKING: [AvatarState.IDLE, AvatarState.LISTENING, AvatarState.THINKING],
    AvatarState.THINKING: [AvatarState.IDLE, AvatarState.LISTENING, AvatarState.SPEAKING],
}


def can_transition(from_state: AvatarState, to_state: AvatarState) -> bool:
    """Check if a state transition is valid."""
    return to_state in STATE_TRANSITIONS.get(from_state, [])


def get_state_config(state: AvatarState) -> StateConfig:
    """Get the configuration for a state."""
    return STATE_CONFIGS.get(state, STATE_CONFIGS[AvatarState.IDLE])
