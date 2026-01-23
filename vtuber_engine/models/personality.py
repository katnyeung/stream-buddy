"""
Personality profiles - Movement style presets for avatar behavior.

Different personalities affect:
- Idle movement amplitude and speed
- Blink frequency and duration
- Head movement range
- Breathing intensity
- Randomness of spontaneous actions
"""
from dataclasses import dataclass
from typing import Dict


@dataclass
class PersonalityProfile:
    """
    Movement style settings that affect all engines.
    """
    name: str

    # Idle engine settings
    breathing_amplitude: float = 1.0      # Multiplier for breathing movement
    breathing_speed: float = 1.0          # Multiplier for breathing speed
    noise_amplitude: float = 1.0          # Multiplier for perlin noise movement
    noise_speed: float = 1.0              # Multiplier for noise change rate

    # Blink settings
    blink_interval_min: float = 2.0       # Minimum seconds between blinks
    blink_interval_max: float = 6.0       # Maximum seconds between blinks
    blink_duration: float = 0.15          # Duration of blink in seconds

    # Head movement
    head_range_multiplier: float = 1.0    # Multiplier for head movement range

    # Randomness engine settings
    spontaneous_action_chance: float = 0.02   # Chance per second for random action
    spontaneous_action_cooldown: float = 5.0  # Minimum seconds between random actions

    # State-specific behavior intensity
    listening_nod_chance: float = 0.15    # Chance to nod while listening
    thinking_look_away_chance: float = 0.3 # Chance to look away while thinking

    # Overall intensity multiplier
    global_intensity: float = 1.0


# Preset personality profiles
PERSONALITY_PRESETS: Dict[str, PersonalityProfile] = {
    "calm": PersonalityProfile(
        name="calm",
        breathing_amplitude=0.8,
        breathing_speed=0.7,
        noise_amplitude=0.5,
        noise_speed=0.6,
        blink_interval_min=3.0,
        blink_interval_max=7.0,
        blink_duration=0.2,
        head_range_multiplier=0.7,
        spontaneous_action_chance=0.01,
        spontaneous_action_cooldown=8.0,
        listening_nod_chance=0.08,
        thinking_look_away_chance=0.2,
        global_intensity=0.8,
    ),

    "neutral": PersonalityProfile(
        name="neutral",
        breathing_amplitude=1.0,
        breathing_speed=1.0,
        noise_amplitude=1.0,
        noise_speed=1.0,
        blink_interval_min=2.0,
        blink_interval_max=6.0,
        blink_duration=0.15,
        head_range_multiplier=1.0,
        spontaneous_action_chance=0.02,
        spontaneous_action_cooldown=5.0,
        listening_nod_chance=0.15,
        thinking_look_away_chance=0.3,
        global_intensity=1.0,
    ),

    "energetic": PersonalityProfile(
        name="energetic",
        breathing_amplitude=1.2,
        breathing_speed=1.3,
        noise_amplitude=1.5,
        noise_speed=1.4,
        blink_interval_min=1.5,
        blink_interval_max=4.0,
        blink_duration=0.12,
        head_range_multiplier=1.3,
        spontaneous_action_chance=0.04,
        spontaneous_action_cooldown=3.0,
        listening_nod_chance=0.25,
        thinking_look_away_chance=0.4,
        global_intensity=1.2,
    ),

    "shy": PersonalityProfile(
        name="shy",
        breathing_amplitude=0.9,
        breathing_speed=1.1,
        noise_amplitude=0.6,
        noise_speed=0.8,
        blink_interval_min=1.5,
        blink_interval_max=4.0,
        blink_duration=0.18,
        head_range_multiplier=0.6,
        spontaneous_action_chance=0.01,
        spontaneous_action_cooldown=10.0,
        listening_nod_chance=0.05,
        thinking_look_away_chance=0.5,
        global_intensity=0.7,
    ),

    "expressive": PersonalityProfile(
        name="expressive",
        breathing_amplitude=1.1,
        breathing_speed=1.0,
        noise_amplitude=1.3,
        noise_speed=1.2,
        blink_interval_min=2.0,
        blink_interval_max=5.0,
        blink_duration=0.15,
        head_range_multiplier=1.4,
        spontaneous_action_chance=0.05,
        spontaneous_action_cooldown=3.0,
        listening_nod_chance=0.3,
        thinking_look_away_chance=0.35,
        global_intensity=1.3,
    ),
}


def get_personality(name: str) -> PersonalityProfile:
    """Get a personality profile by name, defaulting to neutral."""
    return PERSONALITY_PRESETS.get(name.lower(), PERSONALITY_PRESETS["neutral"])
