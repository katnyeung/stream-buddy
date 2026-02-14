"""
Parameter Blender - Combines outputs from all engines into final parameters.

Layer priorities (highest to lowest):
1. LipSync - mouth control
2. Action (Gestures) - one-shot animations
3. Action (Mood) - persistent expression
4. State - state-specific behaviors
5. Randomness - spontaneous actions
6. Idle - base ambient movement

Lower priority layers contribute when higher layers don't specify a param.
Some params (like mouthOpen) are exclusively controlled by specific engines.
"""
from typing import Dict, List, Optional, Set

from .models.params import PARAM_DEFAULTS, PARAM_RANGES, clamp_params


class ParameterBlender:
    """
    Combines parameter outputs from multiple engines.
    Handles layer priorities and parameter exclusions.
    """

    # Parameters exclusively controlled by specific engines
    # These are NOT blended - the controlling engine has full authority
    EXCLUSIVE_PARAMS: Dict[str, str] = {
        "mouthOpen": "lipsync",  # Lip sync has exclusive control of mouth
    }

    def __init__(self):
        # Base parameters (from idle engine primarily)
        self._base_params: Dict[str, float] = PARAM_DEFAULTS.copy()

        # Engine outputs by layer (ordered by priority, highest first)
        self._layers: Dict[str, Dict[str, float]] = {
            "lipsync": {},
            "action": {},      # Mood + gestures
            "state": {},
            "randomness": {},
            "idle": {},
        }

        # Parameters to skip entirely
        self._excluded_params: Set[str] = set()

    def set_layer(self, layer_name: str, params: Dict[str, float]) -> None:
        """
        Set parameters for a specific layer.

        Args:
            layer_name: Name of the layer (lipsync, action, state, randomness, idle)
            params: Parameter values from the engine
        """
        if layer_name in self._layers:
            self._layers[layer_name] = params.copy()

    def clear_layer(self, layer_name: str) -> None:
        """Clear all parameters from a layer."""
        if layer_name in self._layers:
            self._layers[layer_name] = {}

    def exclude_param(self, param_name: str) -> None:
        """Exclude a parameter from blending."""
        self._excluded_params.add(param_name)

    def include_param(self, param_name: str) -> None:
        """Re-include a parameter."""
        self._excluded_params.discard(param_name)

    def blend(self) -> Dict[str, float]:
        """
        Blend all layers into final parameter values.

        Returns:
            Dict of blended parameters, clamped to valid ranges
        """
        # Start with base defaults
        result = self._base_params.copy()

        # Apply layers from lowest to highest priority
        # Higher priority overrides lower
        for layer_name in reversed(["idle", "randomness", "state", "action", "lipsync"]):
            layer_params = self._layers.get(layer_name, {})

            for param, value in layer_params.items():
                # Skip excluded params
                if param in self._excluded_params:
                    continue

                # Skip private params (used for inter-engine communication)
                if param.startswith("_"):
                    continue

                # Check if param is exclusively controlled
                exclusive_engine = self.EXCLUSIVE_PARAMS.get(param)
                if exclusive_engine and exclusive_engine != layer_name:
                    # This param is controlled by another engine
                    continue

                result[param] = value

        # Clamp all values to valid ranges
        return clamp_params(result)

    def blend_additive(self) -> Dict[str, float]:
        """
        Blend layers additively (for relative gesture values).
        Idle provides base, higher layers add to it.

        Returns:
            Dict of blended parameters
        """
        # Start with base defaults
        result = self._base_params.copy()

        # Layer order for additive blending
        additive_layers = ["idle", "randomness", "state"]
        override_layers = ["action", "lipsync"]  # These override, not add

        # Add lower-priority layers
        for layer_name in additive_layers:
            layer_params = self._layers.get(layer_name, {})
            for param, value in layer_params.items():
                if param in self._excluded_params or param.startswith("_"):
                    continue
                result[param] = result.get(param, 0) + value

        # Override with higher-priority layers
        for layer_name in override_layers:
            layer_params = self._layers.get(layer_name, {})
            for param, value in layer_params.items():
                if param in self._excluded_params or param.startswith("_"):
                    continue

                exclusive_engine = self.EXCLUSIVE_PARAMS.get(param)
                if exclusive_engine and exclusive_engine != layer_name:
                    continue

                result[param] = value

        return clamp_params(result)

    def get_triggered_gestures(self) -> List[str]:
        """
        Get gestures triggered by state/randomness engines.
        These are communicated via _trigger_gesture param.
        """
        gestures = []

        for layer_name in ["state", "randomness"]:
            layer_params = self._layers.get(layer_name, {})
            gesture = layer_params.get("_trigger_gesture")
            if gesture:
                gestures.append(gesture)

        return gestures

    def reset(self) -> None:
        """Reset all layers to empty."""
        for layer_name in self._layers:
            self._layers[layer_name] = {}
        self._excluded_params.clear()

    @property
    def base_params(self) -> Dict[str, float]:
        """Get base parameters."""
        return self._base_params.copy()

    def set_base_params(self, params: Dict[str, float]) -> None:
        """Set base parameters."""
        self._base_params = params.copy()
