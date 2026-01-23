"""
Action definitions - Moods and gestures ported from JavaScript action-library.js

Moods: Persistent expressions (stay until changed)
Gestures: One-shot animations (play once and return)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MoodDefinition:
    """A mood is a persistent expression with target parameters."""
    name: str
    params: Dict[str, float]
    transition_ms: int = 400  # Time to transition to this mood


@dataclass
class GestureKeyframe:
    """A single keyframe in a gesture animation."""
    t: float  # Progress 0-1
    params: Dict[str, float]  # Parameter values at this keyframe


@dataclass
class GestureDefinition:
    """A gesture is a one-shot animation with keyframes."""
    name: str
    keyframes: List[GestureKeyframe]
    duration_ms: int
    relative: bool = True  # If True, values are added to current; if False, absolute


# ============================================
# MOODS - Persistent expressions (ported from JS)
# ============================================
MOODS: Dict[str, MoodDefinition] = {
    "neutral": MoodDefinition(
        name="neutral",
        params={"angleX": 0, "angleY": 0, "angleZ": 2, "mouthForm": 0, "eyeOpenL": 1, "eyeOpenR": 1, "eyeBallX": 0, "eyeBallY": 0, "browLY": 0, "browRY": 0},
        transition_ms=400
    ),
    "happy": MoodDefinition(
        name="happy",
        params={"angleX": 5, "angleY": -3, "angleZ": 3, "mouthForm": 0.7, "eyeOpenL": 0.85, "eyeOpenR": 0.85, "eyeBallY": -0.1, "browLY": 0.2, "browRY": 0.2},
        transition_ms=400
    ),
    "friendly": MoodDefinition(
        name="friendly",
        params={"angleX": 3, "angleY": -2, "angleZ": 5, "mouthForm": 0.5, "eyeOpenL": 0.9, "eyeOpenR": 0.9, "browLY": 0.1, "browRY": 0.1},
        transition_ms=350
    ),
    "curious": MoodDefinition(
        name="curious",
        params={"angleX": -5, "angleY": 5, "angleZ": 10, "mouthForm": 0.1, "eyeOpenL": 1.1, "eyeOpenR": 1.1, "eyeBallY": -0.2, "browLY": 0.4, "browRY": 0.3},
        transition_ms=500
    ),
    "thinking": MoodDefinition(
        name="thinking",
        params={"angleX": -5, "angleY": 5, "angleZ": 3, "mouthForm": 0.1, "eyeOpenL": 0.8, "eyeOpenR": 0.85, "eyeBallX": 0, "eyeBallY": 0, "browLY": -0.1, "browRY": 0.2},
        transition_ms=600
    ),
    "surprised": MoodDefinition(
        name="surprised",
        params={"angleX": 0, "angleY": -6, "angleZ": 0, "mouthOpen": 0.4, "mouthForm": 0, "eyeOpenL": 1.3, "eyeOpenR": 1.3, "browLY": 0.6, "browRY": 0.6},
        transition_ms=150
    ),
    "sad": MoodDefinition(
        name="sad",
        params={"angleX": -8, "angleY": 12, "angleZ": -3, "mouthForm": -0.4, "eyeOpenL": 0.6, "eyeOpenR": 0.6, "eyeBallY": 0.3, "browLY": -0.4, "browRY": -0.4},
        transition_ms=700
    ),
    "excited": MoodDefinition(
        name="excited",
        params={"angleX": 5, "angleY": -8, "angleZ": 8, "mouthForm": 0.9, "mouthOpen": 0.2, "eyeOpenL": 1.2, "eyeOpenR": 1.2, "browLY": 0.5, "browRY": 0.5},
        transition_ms=250
    ),
    "serious": MoodDefinition(
        name="serious",
        params={"angleX": 0, "angleY": 0, "angleZ": 0, "mouthForm": -0.2, "eyeOpenL": 0.9, "eyeOpenR": 0.9, "browLY": -0.2, "browRY": -0.2},
        transition_ms=500
    ),
    "concerned": MoodDefinition(
        name="concerned",
        params={"angleX": -5, "angleY": 3, "angleZ": -5, "mouthForm": -0.2, "eyeOpenL": 0.95, "eyeOpenR": 0.95, "eyeBallY": -0.1, "browLY": -0.3, "browRY": 0.1},
        transition_ms=450
    ),
    "skeptical": MoodDefinition(
        name="skeptical",
        params={"angleX": -8, "angleY": 5, "angleZ": 8, "mouthForm": -0.1, "eyeOpenL": 0.7, "eyeOpenR": 1.0, "browLY": -0.2, "browRY": 0.3},
        transition_ms=400
    ),
    "confident": MoodDefinition(
        name="confident",
        params={"angleX": 5, "angleY": -5, "angleZ": 0, "mouthForm": 0.3, "eyeOpenL": 0.9, "eyeOpenR": 0.9, "eyeBallY": -0.1, "browLY": 0.1, "browRY": 0.1},
        transition_ms=400
    ),
    "amused": MoodDefinition(
        name="amused",
        params={"angleX": 3, "angleY": -2, "angleZ": 6, "mouthForm": 0.6, "eyeOpenL": 0.75, "eyeOpenR": 0.75, "browLY": 0.2, "browRY": 0.2},
        transition_ms=350
    ),
    "embarrassed": MoodDefinition(
        name="embarrassed",
        params={"angleX": -10, "angleY": 8, "angleZ": -8, "mouthForm": 0.2, "eyeOpenL": 0.7, "eyeOpenR": 0.7, "eyeBallX": 0.3, "eyeBallY": 0.2},
        transition_ms=400
    ),
    "annoyed": MoodDefinition(
        name="annoyed",
        params={"angleX": -3, "angleY": 0, "angleZ": 0, "mouthForm": -0.3, "eyeOpenL": 0.8, "eyeOpenR": 0.8, "browLY": -0.4, "browRY": -0.4},
        transition_ms=350
    ),
    "proud": MoodDefinition(
        name="proud",
        params={"angleX": 8, "angleY": -8, "angleZ": 0, "mouthForm": 0.4, "eyeOpenL": 0.85, "eyeOpenR": 0.85, "eyeBallY": -0.2},
        transition_ms=500
    ),
    "shy": MoodDefinition(
        name="shy",
        params={"angleX": -12, "angleY": 10, "angleZ": 10, "mouthForm": 0.2, "eyeOpenL": 0.6, "eyeOpenR": 0.6, "eyeBallX": 0.4, "eyeBallY": 0.2},
        transition_ms=500
    ),
    "determined": MoodDefinition(
        name="determined",
        params={"angleX": 0, "angleY": -5, "angleZ": 0, "mouthForm": 0, "eyeOpenL": 1.0, "eyeOpenR": 1.0, "browLY": -0.2, "browRY": -0.2},
        transition_ms=400
    ),
    "sleepy": MoodDefinition(
        name="sleepy",
        params={"angleX": -5, "angleY": 5, "angleZ": -5, "mouthForm": 0, "eyeOpenL": 0.4, "eyeOpenR": 0.4, "eyeBallY": 0.2},
        transition_ms=800
    ),
    "mischievous": MoodDefinition(
        name="mischievous",
        params={"angleX": 5, "angleY": -3, "angleZ": 8, "mouthForm": 0.5, "eyeOpenL": 0.9, "eyeOpenR": 0.7, "browLY": 0.3, "browRY": -0.1},
        transition_ms=350
    ),
}


def _kf(t: float, **params) -> GestureKeyframe:
    """Helper to create a keyframe."""
    return GestureKeyframe(t=t, params=params)


# ============================================
# GESTURES - One-shot animations (ported from JS)
# ============================================
GESTURES: Dict[str, GestureDefinition] = {
    # === HEAD NODS ===
    "nod": GestureDefinition(
        name="nod",
        keyframes=[_kf(0.0, angleY=0), _kf(0.25, angleY=-12), _kf(0.5, angleY=0), _kf(0.75, angleY=-8), _kf(1.0, angleY=0)],
        duration_ms=1000, relative=True
    ),
    "nod_slow": GestureDefinition(
        name="nod_slow",
        keyframes=[_kf(0.0, angleY=0), _kf(0.3, angleY=-12), _kf(0.6, angleY=0), _kf(1.0, angleY=0)],
        duration_ms=1000, relative=True
    ),
    "nod_fast": GestureDefinition(
        name="nod_fast",
        keyframes=[_kf(0.0, angleY=0), _kf(0.2, angleY=-8), _kf(0.4, angleY=0), _kf(0.6, angleY=-6), _kf(0.8, angleY=0), _kf(1.0, angleY=0)],
        duration_ms=400, relative=True
    ),
    "nod_double": GestureDefinition(
        name="nod_double",
        keyframes=[_kf(0.0, angleY=0), _kf(0.15, angleY=-10), _kf(0.3, angleY=0), _kf(0.45, angleY=-10), _kf(0.6, angleY=0), _kf(1.0, angleY=0)],
        duration_ms=700, relative=True
    ),
    "nod_big": GestureDefinition(
        name="nod_big",
        keyframes=[_kf(0.0, angleY=0), _kf(0.3, angleY=-18), _kf(0.6, angleY=0), _kf(1.0, angleY=0)],
        duration_ms=800, relative=True
    ),

    # === HEAD SHAKES ===
    "shake": GestureDefinition(
        name="shake",
        keyframes=[_kf(0.0, angleX=0), _kf(0.15, angleX=12), _kf(0.35, angleX=-12), _kf(0.55, angleX=8), _kf(0.75, angleX=-5), _kf(1.0, angleX=0)],
        duration_ms=700, relative=True
    ),
    "shake_slow": GestureDefinition(
        name="shake_slow",
        keyframes=[_kf(0.0, angleX=0), _kf(0.2, angleX=15), _kf(0.5, angleX=-15), _kf(0.8, angleX=8), _kf(1.0, angleX=0)],
        duration_ms=1200, relative=True
    ),
    "shake_fast": GestureDefinition(
        name="shake_fast",
        keyframes=[_kf(0.0, angleX=0), _kf(0.1, angleX=10), _kf(0.25, angleX=-10), _kf(0.4, angleX=8), _kf(0.55, angleX=-6), _kf(0.7, angleX=4), _kf(1.0, angleX=0)],
        duration_ms=500, relative=True
    ),
    "shake_small": GestureDefinition(
        name="shake_small",
        keyframes=[_kf(0.0, angleX=0), _kf(0.2, angleX=5), _kf(0.4, angleX=-5), _kf(0.6, angleX=3), _kf(1.0, angleX=0)],
        duration_ms=500, relative=True
    ),

    # === HEAD TILTS ===
    "tilt": GestureDefinition(
        name="tilt",
        keyframes=[_kf(0.0, angleZ=0), _kf(0.3, angleZ=15), _kf(0.7, angleZ=15), _kf(1.0, angleZ=0)],
        duration_ms=1000, relative=True
    ),
    "tilt_left": GestureDefinition(
        name="tilt_left",
        keyframes=[_kf(0.0, angleZ=0), _kf(0.3, angleZ=18), _kf(0.7, angleZ=18), _kf(1.0, angleZ=0)],
        duration_ms=1200, relative=True
    ),
    "tilt_right": GestureDefinition(
        name="tilt_right",
        keyframes=[_kf(0.0, angleZ=0), _kf(0.3, angleZ=-18), _kf(0.7, angleZ=-18), _kf(1.0, angleZ=0)],
        duration_ms=1200, relative=True
    ),
    "tilt_curious": GestureDefinition(
        name="tilt_curious",
        keyframes=[_kf(0.0, angleZ=0, browLY=0, browRY=0), _kf(0.3, angleZ=20, browLY=0.3, browRY=0.2), _kf(0.7, angleZ=20, browLY=0.3, browRY=0.2), _kf(1.0, angleZ=0, browLY=0, browRY=0)],
        duration_ms=1500, relative=True
    ),

    # === EYE MOVEMENTS ===
    "blink": GestureDefinition(
        name="blink",
        keyframes=[_kf(0.0, eyeOpenL=0, eyeOpenR=0), _kf(0.3, eyeOpenL=-1, eyeOpenR=-1), _kf(1.0, eyeOpenL=0, eyeOpenR=0)],
        duration_ms=200, relative=True
    ),
    "blink_slow": GestureDefinition(
        name="blink_slow",
        keyframes=[_kf(0.0, eyeOpenL=0, eyeOpenR=0), _kf(0.3, eyeOpenL=-1, eyeOpenR=-1), _kf(0.6, eyeOpenL=-1, eyeOpenR=-1), _kf(1.0, eyeOpenL=0, eyeOpenR=0)],
        duration_ms=500, relative=True
    ),
    "wink": GestureDefinition(
        name="wink",
        keyframes=[_kf(0.0, eyeOpenL=0), _kf(0.2, eyeOpenL=-0.9), _kf(0.6, eyeOpenL=-0.9), _kf(1.0, eyeOpenL=0)],
        duration_ms=400, relative=True
    ),
    "wink_right": GestureDefinition(
        name="wink_right",
        keyframes=[_kf(0.0, eyeOpenR=0), _kf(0.2, eyeOpenR=-0.9), _kf(0.6, eyeOpenR=-0.9), _kf(1.0, eyeOpenR=0)],
        duration_ms=400, relative=True
    ),
    "eye_roll": GestureDefinition(
        name="eye_roll",
        keyframes=[_kf(0.0, eyeBallX=0, eyeBallY=0), _kf(0.25, eyeBallX=0.5, eyeBallY=-0.5), _kf(0.5, eyeBallX=0, eyeBallY=-0.7), _kf(0.75, eyeBallX=-0.5, eyeBallY=-0.5), _kf(1.0, eyeBallX=0, eyeBallY=0)],
        duration_ms=800, relative=True
    ),
    "look_left": GestureDefinition(
        name="look_left",
        keyframes=[_kf(0.0, eyeBallX=0, angleX=0), _kf(0.2, eyeBallX=-0.7, angleX=-5), _kf(0.7, eyeBallX=-0.7, angleX=-5), _kf(1.0, eyeBallX=0, angleX=0)],
        duration_ms=1200, relative=True
    ),
    "look_right": GestureDefinition(
        name="look_right",
        keyframes=[_kf(0.0, eyeBallX=0, angleX=0), _kf(0.2, eyeBallX=0.7, angleX=5), _kf(0.7, eyeBallX=0.7, angleX=5), _kf(1.0, eyeBallX=0, angleX=0)],
        duration_ms=1200, relative=True
    ),
    "look_up": GestureDefinition(
        name="look_up",
        keyframes=[_kf(0.0, eyeBallY=0, angleY=0), _kf(0.2, eyeBallY=0.5, angleY=8), _kf(0.7, eyeBallY=0.5, angleY=8), _kf(1.0, eyeBallY=0, angleY=0)],
        duration_ms=1000, relative=True
    ),
    "look_down": GestureDefinition(
        name="look_down",
        keyframes=[_kf(0.0, eyeBallY=0, angleY=0), _kf(0.2, eyeBallY=-0.5, angleY=-8), _kf(0.7, eyeBallY=-0.5, angleY=-8), _kf(1.0, eyeBallY=0, angleY=0)],
        duration_ms=1000, relative=True
    ),
    "look_away": GestureDefinition(
        name="look_away",
        keyframes=[_kf(0.0, eyeBallX=0, angleX=0, angleZ=0), _kf(0.25, eyeBallX=0.6, angleX=8, angleZ=-5), _kf(0.65, eyeBallX=0.6, angleX=8, angleZ=-5), _kf(1.0, eyeBallX=0, angleX=0, angleZ=0)],
        duration_ms=1500, relative=True
    ),
    "glance_left": GestureDefinition(
        name="glance_left",
        keyframes=[_kf(0.0, eyeBallX=0), _kf(0.15, eyeBallX=-0.6), _kf(0.4, eyeBallX=-0.6), _kf(0.6, eyeBallX=0), _kf(1.0, eyeBallX=0)],
        duration_ms=600, relative=True
    ),
    "glance_right": GestureDefinition(
        name="glance_right",
        keyframes=[_kf(0.0, eyeBallX=0), _kf(0.15, eyeBallX=0.6), _kf(0.4, eyeBallX=0.6), _kf(0.6, eyeBallX=0), _kf(1.0, eyeBallX=0)],
        duration_ms=600, relative=True
    ),

    # === EYEBROW MOVEMENTS ===
    "raise_brows": GestureDefinition(
        name="raise_brows",
        keyframes=[_kf(0.0, browLY=0, browRY=0, eyeOpenL=0, eyeOpenR=0), _kf(0.2, browLY=0.5, browRY=0.5, eyeOpenL=0.2, eyeOpenR=0.2), _kf(0.7, browLY=0.5, browRY=0.5, eyeOpenL=0.2, eyeOpenR=0.2), _kf(1.0, browLY=0, browRY=0, eyeOpenL=0, eyeOpenR=0)],
        duration_ms=800, relative=True
    ),
    "raise_brow_left": GestureDefinition(
        name="raise_brow_left",
        keyframes=[_kf(0.0, browLY=0), _kf(0.2, browLY=0.6), _kf(0.7, browLY=0.6), _kf(1.0, browLY=0)],
        duration_ms=800, relative=True
    ),
    "raise_brow_right": GestureDefinition(
        name="raise_brow_right",
        keyframes=[_kf(0.0, browRY=0), _kf(0.2, browRY=0.6), _kf(0.7, browRY=0.6), _kf(1.0, browRY=0)],
        duration_ms=800, relative=True
    ),
    "furrow_brows": GestureDefinition(
        name="furrow_brows",
        keyframes=[_kf(0.0, browLY=0, browRY=0), _kf(0.2, browLY=-0.4, browRY=-0.4), _kf(0.7, browLY=-0.4, browRY=-0.4), _kf(1.0, browLY=0, browRY=0)],
        duration_ms=900, relative=True
    ),

    # === BODY MOVEMENTS ===
    "lean_in": GestureDefinition(
        name="lean_in",
        keyframes=[_kf(0.0, angleY=0, bodyAngleY=0), _kf(0.3, angleY=-5, bodyAngleY=-3), _kf(0.7, angleY=-5, bodyAngleY=-3), _kf(1.0, angleY=0, bodyAngleY=0)],
        duration_ms=1200, relative=True
    ),
    "lean_back": GestureDefinition(
        name="lean_back",
        keyframes=[_kf(0.0, angleY=0, bodyAngleY=0), _kf(0.3, angleY=5, bodyAngleY=3), _kf(0.7, angleY=5, bodyAngleY=3), _kf(1.0, angleY=0, bodyAngleY=0)],
        duration_ms=1200, relative=True
    ),
    "shrug": GestureDefinition(
        name="shrug",
        keyframes=[_kf(0.0, angleZ=0, browLY=0, browRY=0, bodyAngleZ=0), _kf(0.2, angleZ=8, browLY=0.4, browRY=0.4, bodyAngleZ=3), _kf(0.6, angleZ=8, browLY=0.4, browRY=0.4, bodyAngleZ=3), _kf(1.0, angleZ=0, browLY=0, browRY=0, bodyAngleZ=0)],
        duration_ms=900, relative=True
    ),
    "ponder": GestureDefinition(
        name="ponder",
        keyframes=[_kf(0.0, angleX=0, angleY=0, eyeBallX=0, eyeBallY=0), _kf(0.2, angleX=-10, angleY=8, eyeBallX=-0.4, eyeBallY=0.3), _kf(0.8, angleX=-10, angleY=8, eyeBallX=-0.4, eyeBallY=0.3), _kf(1.0, angleX=0, angleY=0, eyeBallX=0, eyeBallY=0)],
        duration_ms=2000, relative=True
    ),
    "sway": GestureDefinition(
        name="sway",
        keyframes=[_kf(0.0, bodyAngleX=0), _kf(0.25, bodyAngleX=5), _kf(0.75, bodyAngleX=-5), _kf(1.0, bodyAngleX=0)],
        duration_ms=1500, relative=True
    ),
    "lean_left": GestureDefinition(
        name="lean_left",
        keyframes=[_kf(0.0, bodyAngleX=0, angleZ=0), _kf(0.3, bodyAngleX=8, angleZ=5), _kf(0.7, bodyAngleX=8, angleZ=5), _kf(1.0, bodyAngleX=0, angleZ=0)],
        duration_ms=1000, relative=True
    ),
    "lean_right": GestureDefinition(
        name="lean_right",
        keyframes=[_kf(0.0, bodyAngleX=0, angleZ=0), _kf(0.3, bodyAngleX=-8, angleZ=-5), _kf(0.7, bodyAngleX=-8, angleZ=-5), _kf(1.0, bodyAngleX=0, angleZ=0)],
        duration_ms=1000, relative=True
    ),
    "sway_talk": GestureDefinition(
        name="sway_talk",
        keyframes=[_kf(0.0, bodyAngleX=0, angleZ=0), _kf(0.2, bodyAngleX=4, angleZ=3), _kf(0.5, bodyAngleX=-4, angleZ=-3), _kf(0.8, bodyAngleX=3, angleZ=2), _kf(1.0, bodyAngleX=0, angleZ=0)],
        duration_ms=2000, relative=True
    ),
    "idle_sway": GestureDefinition(
        name="idle_sway",
        keyframes=[_kf(0.0, angleZ=0, angleY=0), _kf(0.25, angleZ=3, angleY=-2), _kf(0.5, angleZ=0, angleY=0), _kf(0.75, angleZ=-3, angleY=2), _kf(1.0, angleZ=0, angleY=0)],
        duration_ms=4000, relative=True
    ),
    "idle_breathe": GestureDefinition(
        name="idle_breathe",
        keyframes=[_kf(0.0, angleY=0, bodyAngleY=0), _kf(0.5, angleY=2, bodyAngleY=1), _kf(1.0, angleY=0, bodyAngleY=0)],
        duration_ms=3000, relative=True
    ),
    "bounce": GestureDefinition(
        name="bounce",
        keyframes=[_kf(0.0, bodyAngleY=0), _kf(0.15, bodyAngleY=-5), _kf(0.3, bodyAngleY=0), _kf(0.45, bodyAngleY=-4), _kf(0.6, bodyAngleY=0), _kf(0.75, bodyAngleY=-2), _kf(1.0, bodyAngleY=0)],
        duration_ms=600, relative=True
    ),

    # === HAND/ARM GESTURES (ABSOLUTE - not relative) ===
    "wave": GestureDefinition(
        name="wave",
        keyframes=[
            _kf(0.0, armLB=-1, armLA=-1, handChangeR=0, handAngleR=0),
            _kf(0.15, armLB=5, armLA=-1, handChangeR=1, handAngleR=0.5),
            _kf(0.25, armLB=5, armLA=-1, handChangeR=1, handAngleR=-0.5),
            _kf(0.35, armLB=5, armLA=-1, handChangeR=1, handAngleR=0.5),
            _kf(0.45, armLB=5, armLA=-1, handChangeR=1, handAngleR=-0.5),
            _kf(0.55, armLB=5, armLA=-1, handChangeR=1, handAngleR=0.5),
            _kf(0.7, armLB=5, armLA=-1, handChangeR=1, handAngleR=0),
            _kf(0.85, armLB=2, armLA=-1, handChangeR=0.5, handAngleR=0),
            _kf(1.0, armLB=-1, armLA=-1, handChangeR=0, handAngleR=0)
        ],
        duration_ms=1400, relative=False
    ),
    "wave_small": GestureDefinition(
        name="wave_small",
        keyframes=[
            _kf(0.0, armLB=-1, armLA=-1, handChangeR=0, handAngleR=0),
            _kf(0.2, armLB=3, armLA=-1, handChangeR=1, handAngleR=0.3),
            _kf(0.35, armLB=3, armLA=-1, handChangeR=1, handAngleR=-0.3),
            _kf(0.5, armLB=3, armLA=-1, handChangeR=1, handAngleR=0.3),
            _kf(0.65, armLB=3, armLA=-1, handChangeR=1, handAngleR=-0.3),
            _kf(0.8, armLB=1.5, armLA=-1, handChangeR=0.5, handAngleR=0),
            _kf(1.0, armLB=-1, armLA=-1, handChangeR=0, handAngleR=0)
        ],
        duration_ms=1000, relative=False
    ),
    "point": GestureDefinition(
        name="point",
        keyframes=[_kf(0.0, armRB=-1, armRA=-1), _kf(0.3, armRB=2, armRA=-1), _kf(0.7, armRB=2, armRA=-1), _kf(1.0, armRB=-1, armRA=-1)],
        duration_ms=1200, relative=False
    ),
    "hands_up": GestureDefinition(
        name="hands_up",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.3, armLB=4, armRB=4, armLA=-1, armRA=-1, handChangeL=1, handChangeR=1),
            _kf(0.7, armLB=4, armRB=4, armLA=-1, armRA=-1, handChangeL=1, handChangeR=1),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1200, relative=False
    ),
    "clap": GestureDefinition(
        name="clap",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.1, armLB=1.5, armRB=1.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0.5),
            _kf(0.2, armLB=1, armRB=1, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0.5),
            _kf(0.3, armLB=1.5, armRB=1.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0.5),
            _kf(0.4, armLB=1, armRB=1, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0.5),
            _kf(0.5, armLB=1.5, armRB=1.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0.5),
            _kf(0.65, armLB=0.5, armRB=0.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0.5),
            _kf(0.8, armLB=0, armRB=0, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1200, relative=False
    ),
    "thumbs_up": GestureDefinition(
        name="thumbs_up",
        keyframes=[_kf(0.0, armRB=-1, armRA=-1, handChangeL=0), _kf(0.25, armRB=2, armRA=-1, handChangeL=1), _kf(0.7, armRB=2, armRA=-1, handChangeL=1), _kf(1.0, armRB=-1, armRA=-1, handChangeL=0)],
        duration_ms=1200, relative=False
    ),
    "facepalm": GestureDefinition(
        name="facepalm",
        keyframes=[_kf(0.0, armRB=-1, armRA=-1, angleY=0), _kf(0.3, armRB=4, armRA=-1, angleY=8), _kf(0.7, armRB=4, armRA=-1, angleY=8), _kf(1.0, armRB=-1, armRA=-1, angleY=0)],
        duration_ms=1500, relative=False
    ),
    "hand_on_chest": GestureDefinition(
        name="hand_on_chest",
        keyframes=[_kf(0.0, armRB=-1, armRA=-1), _kf(0.3, armRB=0.5, armRA=-1), _kf(0.7, armRB=0.5, armRA=-1), _kf(1.0, armRB=-1, armRA=-1)],
        duration_ms=1200, relative=False
    ),
    "present": GestureDefinition(
        name="present",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.2, armLB=3.8, armRB=5.0, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(0.7, armLB=3.8, armRB=5.0, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1500, relative=False
    ),
    "present_both": GestureDefinition(
        name="present_both",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.2, armLB=2.7, armRB=2.7, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.7, armLB=2.7, armRB=2.7, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1800, relative=False
    ),
    "think_hand": GestureDefinition(
        name="think_hand",
        keyframes=[
            _kf(0.0, armRB=-1, armRA=-1, handChangeL=0, angleX=0, angleY=0),
            _kf(0.25, armRB=3.5, armRA=-1, handChangeL=0.5, angleX=-8, angleY=5),
            _kf(0.7, armRB=3.5, armRA=-1, handChangeL=0.5, angleX=-8, angleY=5),
            _kf(1.0, armRB=-1, armRA=-1, handChangeL=0, angleX=0, angleY=0)
        ],
        duration_ms=2000, relative=False
    ),
    "make_point": GestureDefinition(
        name="make_point",
        keyframes=[
            _kf(0.0, armRB=-1, armRA=-1, handChangeL=0),
            _kf(0.15, armRB=2, armRA=-1, handChangeL=1),
            _kf(0.25, armRB=2.3, armRA=-1, handChangeL=1),
            _kf(0.5, armRB=2, armRA=-1, handChangeL=1),
            _kf(0.7, armRB=1.5, armRA=-1, handChangeL=0.5),
            _kf(1.0, armRB=-1, armRA=-1, handChangeL=0)
        ],
        duration_ms=1200, relative=False
    ),
    "emphasize": GestureDefinition(
        name="emphasize",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.1, armLB=0.7, armRB=3.2, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(0.2, armLB=1.0, armRB=3.5, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(0.35, armLB=0.7, armRB=3.2, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(0.5, armLB=1.0, armRB=3.5, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(0.7, armLB=0.5, armRB=2.5, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1000, relative=False
    ),
    "welcome": GestureDefinition(
        name="welcome",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0, angleX=0),
            _kf(0.15, armLB=5.0, armRB=1.6, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=1, angleX=5),
            _kf(0.3, armLB=4.5, armRB=1.6, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=1, angleX=5),
            _kf(0.45, armLB=5.0, armRB=1.6, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=1, angleX=5),
            _kf(0.6, armLB=4.5, armRB=1.6, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=1, angleX=3),
            _kf(0.75, armLB=5.0, armRB=1.6, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=1, angleX=3),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0, angleX=0)
        ],
        duration_ms=1600, relative=False
    ),
    "question_hand": GestureDefinition(
        name="question_hand",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0, angleZ=0),
            _kf(0.2, armLB=2.8, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5, angleZ=8),
            _kf(0.6, armLB=2.8, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5, angleZ=10),
            _kf(0.8, armLB=2.8, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0.5, angleZ=8),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0, angleZ=0)
        ],
        duration_ms=1400, relative=False
    ),
    "calm_down": GestureDefinition(
        name="calm_down",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.2, armLB=2.1, armRB=0.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.4, armLB=1.8, armRB=0.3, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.6, armLB=1.5, armRB=0.1, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.8, armLB=1.0, armRB=-0.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1600, relative=False
    ),
    "acknowledge_hand": GestureDefinition(
        name="acknowledge_hand",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.2, armLB=-0.5, armRB=2.8, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.5, armLB=-0.5, armRB=3.0, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.7, armLB=-0.5, armRB=2.8, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1000, relative=False
    ),
    "excited_hands": GestureDefinition(
        name="excited_hands",
        keyframes=[
            _kf(0.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0),
            _kf(0.1, armLB=4.5, armRB=4.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.2, armLB=5.0, armRB=5.0, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.35, armLB=4.5, armRB=4.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.5, armLB=5.0, armRB=5.0, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(0.7, armLB=3.5, armRB=3.5, armLA=-1, armRA=-1, handChangeL=0.5, handChangeR=0),
            _kf(1.0, armLB=-1, armRB=-1, armLA=-1, armRA=-1, handChangeL=0, handChangeR=0)
        ],
        duration_ms=1200, relative=False
    ),

    # === COMPLEX COMBINED GESTURES (RELATIVE) ===
    "laugh": GestureDefinition(
        name="laugh",
        keyframes=[
            _kf(0.0, mouthOpen=0, angleY=0, eyeOpenL=0, eyeOpenR=0),
            _kf(0.1, mouthOpen=0.4, angleY=-3, eyeOpenL=-0.2, eyeOpenR=-0.2),
            _kf(0.2, mouthOpen=0.2, angleY=0, eyeOpenL=-0.1, eyeOpenR=-0.1),
            _kf(0.3, mouthOpen=0.5, angleY=-3, eyeOpenL=-0.2, eyeOpenR=-0.2),
            _kf(0.4, mouthOpen=0.2, angleY=0, eyeOpenL=-0.1, eyeOpenR=-0.1),
            _kf(0.5, mouthOpen=0.4, angleY=-2, eyeOpenL=-0.2, eyeOpenR=-0.2),
            _kf(0.7, mouthOpen=0.2, angleY=0, eyeOpenL=-0.1, eyeOpenR=-0.1),
            _kf(1.0, mouthOpen=0, angleY=0, eyeOpenL=0, eyeOpenR=0)
        ],
        duration_ms=1200, relative=True
    ),
    "gasp": GestureDefinition(
        name="gasp",
        keyframes=[
            _kf(0.0, mouthOpen=0, eyeOpenL=0, eyeOpenR=0, browLY=0, browRY=0),
            _kf(0.15, mouthOpen=0.6, eyeOpenL=0.3, eyeOpenR=0.3, browLY=0.5, browRY=0.5),
            _kf(0.6, mouthOpen=0.5, eyeOpenL=0.3, eyeOpenR=0.3, browLY=0.5, browRY=0.5),
            _kf(1.0, mouthOpen=0, eyeOpenL=0, eyeOpenR=0, browLY=0, browRY=0)
        ],
        duration_ms=1000, relative=True
    ),
    "sigh": GestureDefinition(
        name="sigh",
        keyframes=[
            _kf(0.0, angleY=0, eyeOpenL=0, eyeOpenR=0, mouthOpen=0),
            _kf(0.2, angleY=5, eyeOpenL=-0.3, eyeOpenR=-0.3, mouthOpen=0.2),
            _kf(0.5, angleY=8, eyeOpenL=-0.3, eyeOpenR=-0.3, mouthOpen=0.3),
            _kf(0.8, angleY=5, eyeOpenL=-0.2, eyeOpenR=-0.2, mouthOpen=0.1),
            _kf(1.0, angleY=0, eyeOpenL=0, eyeOpenR=0, mouthOpen=0)
        ],
        duration_ms=1500, relative=True
    ),
    "startle": GestureDefinition(
        name="startle",
        keyframes=[
            _kf(0.0, angleY=0, eyeOpenL=0, eyeOpenR=0, browLY=0, browRY=0, bodyAngleY=0),
            _kf(0.1, angleY=-8, eyeOpenL=0.4, eyeOpenR=0.4, browLY=0.6, browRY=0.6, bodyAngleY=-3),
            _kf(0.4, angleY=-5, eyeOpenL=0.3, eyeOpenR=0.3, browLY=0.5, browRY=0.5, bodyAngleY=-2),
            _kf(1.0, angleY=0, eyeOpenL=0, eyeOpenR=0, browLY=0, browRY=0, bodyAngleY=0)
        ],
        duration_ms=800, relative=True
    ),
    "double_take": GestureDefinition(
        name="double_take",
        keyframes=[
            _kf(0.0, angleX=0, eyeBallX=0),
            _kf(0.15, angleX=10, eyeBallX=0.5),
            _kf(0.3, angleX=0, eyeBallX=0),
            _kf(0.4, angleX=15, eyeBallX=0.7, eyeOpenL=0.2, eyeOpenR=0.2),
            _kf(0.7, angleX=15, eyeBallX=0.7, eyeOpenL=0.2, eyeOpenR=0.2),
            _kf(1.0, angleX=0, eyeBallX=0, eyeOpenL=0, eyeOpenR=0)
        ],
        duration_ms=1200, relative=True
    ),
}


# Gesture aliases for LLM convenience
GESTURE_ALIASES: Dict[str, Dict[str, str]] = {
    "eye": {
        "blink": "blink", "blink_slow": "blink_slow", "wink": "wink",
        "wink_left": "wink", "wink_right": "wink_right", "roll": "eye_roll",
        "lookup": "look_up", "look_up": "look_up", "lookdown": "look_down",
        "look_down": "look_down", "left": "look_left", "look_left": "look_left",
        "right": "look_right", "look_right": "look_right", "away": "look_away",
        "look_away": "look_away", "glance_left": "glance_left", "glance_right": "glance_right"
    },
    "head": {
        "nod": "nod", "nod_slow": "nod_slow", "nod_fast": "nod_fast",
        "nod_double": "nod_double", "nod_big": "nod_big", "shake": "shake",
        "shake_slow": "shake_slow", "shake_fast": "shake_fast", "shake_small": "shake_small",
        "tilt": "tilt", "tilt_left": "tilt_left", "tilt_right": "tilt_right",
        "tilt_curious": "tilt_curious", "curious": "tilt_curious",
        "lookup": "look_up", "look_up": "look_up", "think": "ponder", "ponder": "ponder"
    },
    "body": {
        "lean": "lean_in", "lean_in": "lean_in", "lean_forward": "lean_in",
        "lean_back": "lean_back", "back": "lean_back", "lean_left": "lean_left",
        "left": "lean_left", "lean_right": "lean_right", "right": "lean_right",
        "shrug": "shrug", "ponder": "ponder", "sway": "sway", "sway_talk": "sway_talk",
        "talk": "sway_talk", "bounce": "bounce", "laugh": "laugh", "gasp": "gasp",
        "sigh": "sigh", "startle": "startle"
    },
    "brow": {
        "raise": "raise_brows", "raise_both": "raise_brows",
        "raise_left": "raise_brow_left", "raise_right": "raise_brow_right",
        "furrow": "furrow_brows", "frown": "furrow_brows"
    },
}


# Compound actions (mood + gesture combinations)
COMPOUND_ACTIONS: Dict[str, Dict[str, str]] = {
    "greet": {"mood": "friendly", "gesture": "nod"},
    "greet_excited": {"mood": "excited", "gesture": "wave"},
    "agree": {"mood": "happy", "gesture": "nod"},
    "agree_strong": {"mood": "confident", "gesture": "nod_big"},
    "disagree": {"mood": "serious", "gesture": "shake"},
    "disagree_strong": {"mood": "annoyed", "gesture": "shake_fast"},
    "confused": {"mood": "curious", "gesture": "tilt_curious"},
    "consider": {"mood": "thinking", "gesture": "ponder"},
    "emphasize": {"mood": "confident", "gesture": "lean_in"},
    "unsure": {"mood": "concerned", "gesture": "shrug"},
    "notice": {"mood": "surprised", "gesture": "raise_brows"},
    "dismiss": {"mood": "skeptical", "gesture": "look_away"},
    "acknowledge": {"mood": "neutral", "gesture": "nod"},
    "celebrate": {"mood": "excited", "gesture": "bounce"},
    "amuse": {"mood": "amused", "gesture": "laugh"},
    "shock": {"mood": "surprised", "gesture": "gasp"},
    "disappoint": {"mood": "sad", "gesture": "sigh"},
    "doubt": {"mood": "skeptical", "gesture": "raise_brow_right"},
    "flirt": {"mood": "mischievous", "gesture": "wink"},
    "encourage": {"mood": "happy", "gesture": "thumbs_up"},
    "frustrate": {"mood": "annoyed", "gesture": "facepalm"},
}


def get_mood(name: str) -> Optional[MoodDefinition]:
    """Get a mood definition by name."""
    return MOODS.get(name.lower())


def get_gesture(name: str) -> Optional[GestureDefinition]:
    """Get a gesture definition by name."""
    return GESTURES.get(name.lower())


def resolve_alias(category: str, name: str) -> Optional[str]:
    """Resolve an alias to a gesture name."""
    aliases = GESTURE_ALIASES.get(category.lower(), {})
    return aliases.get(name.lower())


def get_compound_action(name: str) -> Optional[Dict[str, str]]:
    """Get a compound action definition."""
    return COMPOUND_ACTIONS.get(name.lower())
