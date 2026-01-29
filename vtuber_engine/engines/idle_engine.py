"""
Idle Engine - Generates ambient idle movement.

Responsible for:
- Breathing animation (subtle body and head movement)
- Layered Perlin noise for organic movement
- Automatic blinking (2-6s random intervals)
"""
import math
import random
from typing import Dict

from .base_engine import BaseEngine
from ..models.state import AvatarState
from ..models.personality import PersonalityProfile
from ..utils.noise import PerlinNoise, MultiNoiseGenerator


class IdleEngine(BaseEngine):
    """
    Engine for ambient idle movement.
    Generates breathing, noise-based movement, and automatic blinks.
    """

    # Noise channel assignments
    CHANNEL_HEAD_X = 0
    CHANNEL_HEAD_Y = 1
    CHANNEL_HEAD_Z = 2
    CHANNEL_BODY_X = 3
    CHANNEL_EYE_X = 4
    CHANNEL_EYE_Y = 5

    def __init__(self, seed: int = None):
        super().__init__(name="idle")

        # Noise generators for organic movement
        self.noise = MultiNoiseGenerator(num_channels=8, seed=seed)

        # Breathing state
        self._breath_time = 0.0
        self._breath_cycle_duration = 4.0  # Seconds per breath

        # Blink state
        self._next_blink_time = random.uniform(2.0, 6.0)
        self._blink_progress = 1.0  # 1.0 = eyes open, 0.0 = eyes closed
        self._is_blinking = False
        self._blink_duration = 0.15

    def update(
        self,
        delta_time: float,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile,
        current_params: Dict[str, float],
    ) -> Dict[str, float]:
        """Generate idle movement parameters."""
        if not self.enabled:
            return {}

        self.tick(delta_time)
        params = {}

        # === BREATHING ===
        breathing = self._update_breathing(delta_time, personality)
        params.update(breathing)

        # === NOISE-BASED MOVEMENT ===
        noise_movement = self._update_noise_movement(personality)
        params.update(noise_movement)

        # === BLINKING ===
        blink = self._update_blink(delta_time, personality, state)
        params.update(blink)

        return params

    def _update_breathing(
        self,
        delta_time: float,
        personality: PersonalityProfile
    ) -> Dict[str, float]:
        """
        Generate breathing animation.
        Subtle up/down movement of body and slight head movement.
        Reduced amplitude for calmer appearance.
        """
        self._breath_time += delta_time * personality.breathing_speed

        # Breathing sine wave
        breath_progress = (self._breath_time % self._breath_cycle_duration) / self._breath_cycle_duration
        breath_wave = math.sin(breath_progress * 2 * math.pi)

        amplitude = personality.breathing_amplitude

        return {
            # Body rises slightly on inhale (reduced from 1.5)
            "bodyAngleY": breath_wave * 0.8 * amplitude,
            # Head follows body slightly (reduced from 0.8)
            "angleY": breath_wave * 0.4 * amplitude,
            # Breath parameter for model (if supported)
            "breath": (breath_wave + 1) / 2 * amplitude,
        }

    def _update_noise_movement(
        self,
        personality: PersonalityProfile
    ) -> Dict[str, float]:
        """
        Generate organic noise-based movement.
        Each parameter uses a different noise channel for independent movement.
        Reduced multipliers for calmer, less bouncy idle animation.
        """
        t = self._time
        amp = personality.noise_amplitude
        speed = personality.noise_speed
        head_mult = personality.head_range_multiplier

        return {
            # Head sway - subtle random looking around (reduced from 3.0/2.0)
            "angleX": self.noise.get_noise(self.CHANNEL_HEAD_X, t, speed * 0.2) * 1.5 * amp * head_mult,
            "angleZ": self.noise.get_noise(self.CHANNEL_HEAD_Z, t, speed * 0.15) * 1.0 * amp * head_mult,

            # Body micro-sway (reduced from 1.5)
            "bodyAngleX": self.noise.get_noise(self.CHANNEL_BODY_X, t, speed * 0.1) * 0.8 * amp,

            # Eye drift - very subtle (reduced)
            "eyeBallX": self.noise.get_noise(self.CHANNEL_EYE_X, t, speed * 0.25) * 0.1 * amp,
            "eyeBallY": self.noise.get_noise(self.CHANNEL_EYE_Y, t, speed * 0.2) * 0.08 * amp,
        }

    def _update_blink(
        self,
        delta_time: float,
        personality: PersonalityProfile,
        state: AvatarState
    ) -> Dict[str, float]:
        """
        Handle automatic blinking.
        Uses random intervals based on personality.
        """
        # Update blink timer
        self._next_blink_time -= delta_time

        # Start a blink
        if self._next_blink_time <= 0 and not self._is_blinking:
            self._is_blinking = True
            self._blink_progress = 1.0
            self._blink_duration = personality.blink_duration

        # Process active blink
        if self._is_blinking:
            # Close eyes quickly, open slowly
            blink_speed = 1.0 / self._blink_duration

            if self._blink_progress > 0:
                # Closing
                self._blink_progress -= delta_time * blink_speed * 3  # Fast close
                if self._blink_progress <= 0:
                    self._blink_progress = 0
            else:
                # Opening
                self._blink_progress += delta_time * blink_speed * 1.5  # Slower open
                if self._blink_progress >= 1.0:
                    self._blink_progress = 1.0
                    self._is_blinking = False
                    # Schedule next blink
                    self._next_blink_time = random.uniform(
                        personality.blink_interval_min,
                        personality.blink_interval_max
                    )

            # Return eye open values (these are RELATIVE - will be added to current)
            eye_close_amount = -(1.0 - self._blink_progress)
            return {
                "eyeOpenL": eye_close_amount,
                "eyeOpenR": eye_close_amount,
            }

        return {}

    def force_blink(self) -> None:
        """Trigger an immediate blink."""
        self._is_blinking = True
        self._blink_progress = 1.0

    def reset(self) -> None:
        """Reset engine state."""
        super().reset()
        self._breath_time = 0.0
        self._next_blink_time = random.uniform(2.0, 6.0)
        self._blink_progress = 1.0
        self._is_blinking = False
