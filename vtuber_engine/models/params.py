"""
Parameter schema with defaults and clamping ranges for Live2D avatar control.

Parameter ranges (typical Live2D):
  angleX/Y/Z: -30 to 30 (head rotation)
  mouthOpen: 0 to 1
  mouthForm: -1 to 1 (frown to smile)
  eyeOpenL/R: 0 to 1.3
  eyeBallX/Y: -1 to 1
  browLY/RY: -1 to 1
  bodyAngleX/Y/Z: -15 to 15
  armLA/armRA: -1 to 1 (arm rotation)
  armLB/armRB: -1 to 5 (arm lift)
  handChangeL/R: 0 to 1 (hand pose)
  handAngleL/R: -1 to 1 (hand rotation)
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Tuple, Optional


# Parameter default values
PARAM_DEFAULTS: Dict[str, float] = {
    # Head
    "angleX": 0.0,
    "angleY": 0.0,
    "angleZ": 2.0,  # Slight tilt for natural look

    # Mouth
    "mouthOpen": 0.0,
    "mouthForm": 0.0,

    # Eyes
    "eyeOpenL": 1.0,
    "eyeOpenR": 1.0,
    "eyeBallX": 0.0,
    "eyeBallY": 0.0,
    "eyeSmileL": 0.0,
    "eyeSmileR": 0.0,

    # Eyebrows
    "browLY": 0.0,
    "browRY": 0.0,

    # Body
    "bodyAngleX": 0.0,
    "bodyAngleY": 0.0,
    "bodyAngleZ": 0.0,

    # Arms - A is rotation, B is lift
    "armLA": -1.0,
    "armRA": -1.0,
    "armLB": -1.0,
    "armRB": -1.0,

    # Hands
    "handChangeL": 0.0,
    "handChangeR": 0.0,
    "handAngleL": 0.0,
    "handAngleR": 0.0,

    # Extra
    "tear": 0.0,
    "tere": 0.0,  # Blush
    "breath": 0.0,

    # Canvas transforms (for zooming in/out, position)
    "pos_x": 0.0,
    "pos_y": 0.0,
    "scale": 1.0,
    "rotation": 0.0,
}

# Parameter min/max ranges
PARAM_RANGES: Dict[str, Tuple[float, float]] = {
    # Head
    "angleX": (-30.0, 30.0),
    "angleY": (-30.0, 30.0),
    "angleZ": (-30.0, 30.0),

    # Mouth
    "mouthOpen": (0.0, 1.0),
    "mouthForm": (-1.0, 1.0),

    # Eyes
    "eyeOpenL": (0.0, 1.3),
    "eyeOpenR": (0.0, 1.3),
    "eyeBallX": (-1.0, 1.0),
    "eyeBallY": (-1.0, 1.0),
    "eyeSmileL": (0.0, 1.0),
    "eyeSmileR": (0.0, 1.0),

    # Eyebrows
    "browLY": (-1.0, 1.0),
    "browRY": (-1.0, 1.0),

    # Body
    "bodyAngleX": (-15.0, 15.0),
    "bodyAngleY": (-15.0, 15.0),
    "bodyAngleZ": (-15.0, 15.0),

    # Arms
    "armLA": (-1.0, 1.0),
    "armRA": (-1.0, 1.0),
    "armLB": (-1.0, 5.0),
    "armRB": (-1.0, 5.0),

    # Hands
    "handChangeL": (0.0, 1.0),
    "handChangeR": (0.0, 1.0),
    "handAngleL": (-1.0, 1.0),
    "handAngleR": (-1.0, 1.0),

    # Extra
    "tear": (0.0, 1.0),
    "tere": (0.0, 1.0),
    "breath": (0.0, 1.0),

    # Canvas transforms
    "pos_x": (-1000.0, 1000.0),
    "pos_y": (-1000.0, 1000.0),
    "scale": (0.1, 3.0),
    "rotation": (-180.0, 180.0),
}


def clamp_params(params: Dict[str, float]) -> Dict[str, float]:
    """Clamp all parameters to their valid ranges."""
    result = {}
    for key, value in params.items():
        if key in PARAM_RANGES:
            min_val, max_val = PARAM_RANGES[key]
            result[key] = max(min_val, min(max_val, value))
        else:
            result[key] = value
    return result


@dataclass
class AvatarParams:
    """
    Complete avatar parameter state.
    All Live2D parameters plus canvas transforms.
    """
    # Head
    angleX: float = 0.0
    angleY: float = 0.0
    angleZ: float = 2.0

    # Mouth
    mouthOpen: float = 0.0
    mouthForm: float = 0.0

    # Eyes
    eyeOpenL: float = 1.0
    eyeOpenR: float = 1.0
    eyeBallX: float = 0.0
    eyeBallY: float = 0.0
    eyeSmileL: float = 0.0
    eyeSmileR: float = 0.0

    # Eyebrows
    browLY: float = 0.0
    browRY: float = 0.0

    # Body
    bodyAngleX: float = 0.0
    bodyAngleY: float = 0.0
    bodyAngleZ: float = 0.0

    # Arms
    armLA: float = -1.0
    armRA: float = -1.0
    armLB: float = -1.0
    armRB: float = -1.0

    # Hands
    handChangeL: float = 0.0
    handChangeR: float = 0.0
    handAngleL: float = 0.0
    handAngleR: float = 0.0

    # Extra
    tear: float = 0.0
    tere: float = 0.0
    breath: float = 0.0

    # Canvas transforms
    pos_x: float = 0.0
    pos_y: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON/Redis serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "AvatarParams":
        """Create from dictionary."""
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def defaults(cls) -> "AvatarParams":
        """Create with default values."""
        return cls(**{k: PARAM_DEFAULTS.get(k, 0.0) for k in PARAM_DEFAULTS if k in [f.name for f in cls.__dataclass_fields__.values()]})

    def clamp(self) -> "AvatarParams":
        """Return a new AvatarParams with all values clamped to valid ranges."""
        clamped = clamp_params(self.to_dict())
        return AvatarParams.from_dict(clamped)

    def merge(self, other: Dict[str, float], replace: bool = False) -> "AvatarParams":
        """
        Merge another dict of params into this one.
        If replace=False, adds values (for relative gestures).
        If replace=True, replaces values (for absolute gestures/moods).
        """
        current = self.to_dict()
        for key, value in other.items():
            if key in current:
                if replace:
                    current[key] = value
                else:
                    current[key] = current[key] + value
        return AvatarParams.from_dict(current).clamp()
