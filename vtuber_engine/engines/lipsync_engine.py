"""
Lip Sync Engine - Processes audio amplitude for mouth movement.

Receives amplitude values from the browser (via WebSocket)
and converts them to smooth mouth_open values.
"""
from typing import Dict

from .base_engine import BaseEngine
from ..models.state import AvatarState
from ..models.personality import PersonalityProfile
from ..utils.easing import smooth_damp


class LipSyncEngine(BaseEngine):
    """
    Engine for lip sync animation.
    Processes audio amplitude to control mouth_open parameter.
    """

    def __init__(self):
        super().__init__(name="lipsync")

        # Current amplitude from browser
        self._amplitude = 0.0

        # Smoothed mouth value
        self._mouth_open = 0.0
        self._mouth_velocity = 0.0

        # Lip sync settings
        self.sensitivity = 1.5
        self.smooth_time_open = 0.05   # Fast response to opening
        self.smooth_time_close = 0.15  # Slower closing for natural feel
        self.min_threshold = 0.02       # Ignore very low amplitudes

        # Speaking state
        self._is_speaking = False

    def update(
        self,
        delta_time: float,
        state: AvatarState,
        mood: str,
        personality: PersonalityProfile,
        current_params: Dict[str, float],
    ) -> Dict[str, float]:
        """Process amplitude and return mouth parameters."""
        if not self.enabled:
            return {}

        self.tick(delta_time)

        # Only process when in speaking state
        if state != AvatarState.SPEAKING:
            # Smoothly close mouth when not speaking
            target = 0.0
            self._mouth_open, self._mouth_velocity = smooth_damp(
                self._mouth_open,
                target,
                self._mouth_velocity,
                self.smooth_time_close,
                delta_time
            )
            self._is_speaking = False
        else:
            self._is_speaking = True
            # Process amplitude
            target = self._process_amplitude(self._amplitude)

            # Use different smooth times for opening vs closing
            smooth_time = self.smooth_time_open if target > self._mouth_open else self.smooth_time_close

            self._mouth_open, self._mouth_velocity = smooth_damp(
                self._mouth_open,
                target,
                self._mouth_velocity,
                smooth_time,
                delta_time
            )

        # Clamp to valid range
        self._mouth_open = max(0.0, min(1.0, self._mouth_open))

        return {
            "mouthOpen": self._mouth_open,
        }

    def _process_amplitude(self, amplitude: float) -> float:
        """
        Process raw amplitude into mouth open value.
        Applies threshold, sensitivity, and curve.
        """
        # Ignore very low amplitudes (noise floor)
        if amplitude < self.min_threshold:
            return 0.0

        # Apply sensitivity
        value = amplitude * self.sensitivity

        # Apply curve for more natural mouth movement
        # Lower amplitudes = smaller mouth opening
        # Higher amplitudes = wider opening with diminishing returns
        value = pow(value, 0.7)

        # Clamp
        return min(1.0, value)

    def set_amplitude(self, amplitude: float) -> None:
        """
        Set the current audio amplitude from browser.

        Args:
            amplitude: Audio amplitude (0-1)
        """
        self._amplitude = max(0.0, min(1.0, amplitude))

    def set_sensitivity(self, sensitivity: float) -> None:
        """
        Set lip sync sensitivity.

        Args:
            sensitivity: Multiplier for amplitude (default 1.5)
        """
        self.sensitivity = max(0.1, min(5.0, sensitivity))

    @property
    def is_speaking(self) -> bool:
        """Check if currently processing speech."""
        return self._is_speaking

    @property
    def current_mouth_open(self) -> float:
        """Get current mouth open value."""
        return self._mouth_open

    def reset(self) -> None:
        """Reset engine state."""
        super().reset()
        self._amplitude = 0.0
        self._mouth_open = 0.0
        self._mouth_velocity = 0.0
        self._is_speaking = False
