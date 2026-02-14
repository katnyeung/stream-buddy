"""
Gesture Processor - MediaPipe-based hand tracking and gesture recognition.

Provides:
1. Hand landmark tracking (for arm mirroring)
2. Command gesture recognition (swipe, thumbs up, wave, point)

Gestures are detected with confidence thresholds and cooldowns
to prevent false positives and rapid-fire triggers.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Tuple

logger = logging.getLogger(__name__)

# MediaPipe imports - optional, gracefully degrade if not available
try:
    import cv2
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("[GestureProcessor] MediaPipe not available. Install with: pip install mediapipe opencv-python")


class GestureType(Enum):
    """Recognized gesture types."""
    NONE = "none"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_LEFT = "swipe_left"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    WAVE = "wave"
    POINT = "point"
    OPEN_PALM = "open_palm"
    FIST = "fist"


@dataclass
class HandLandmarks:
    """Processed hand landmark data for avatar mirroring."""
    # Wrist position (normalized 0-1)
    wrist_x: float
    wrist_y: float

    # Arm lift value for avatar (0-5 range like armLB/armRB)
    arm_lift: float

    # Hand pose (0-1, 0=closed fist, 1=open palm)
    hand_openness: float

    # Which hand (left/right from camera's perspective)
    is_left_hand: bool

    # Confidence
    confidence: float


@dataclass
class DetectedGesture:
    """A detected gesture with metadata."""
    gesture_type: GestureType
    confidence: float
    timestamp: float
    hand_side: str  # 'left', 'right', or 'both'


class GestureProcessor:
    """
    Processes camera frames for hand tracking and gesture recognition.

    Usage:
        processor = GestureProcessor()
        await processor.start()

        # In camera loop:
        landmarks, gesture = processor.process_frame(frame)
        if gesture:
            print(f"Detected: {gesture.gesture_type}")

        await processor.stop()
    """

    def __init__(self, camera_index: int = 0):
        """
        Initialize gesture processor.

        Args:
            camera_index: OpenCV camera index (0 = default webcam)
        """
        self.camera_index = camera_index
        self.running = False
        self.cap = None

        # MediaPipe components
        self.mp_hands = None
        self.hands = None
        self.mp_drawing = None

        # Gesture detection state
        self.last_gesture_time: Dict[GestureType, float] = {}
        self.gesture_cooldown = 1.0  # Seconds between same gesture
        self.min_confidence = 0.8

        # Motion tracking for swipe detection
        self.hand_history: Dict[str, List[Tuple[float, float, float]]] = {
            'left': [],
            'right': []
        }
        self.history_max_length = 10
        self.swipe_velocity_threshold = 0.15  # Normalized units per frame

        # Wave detection
        self.wave_oscillation_count: Dict[str, int] = {'left': 0, 'right': 0}
        self.wave_last_direction: Dict[str, Optional[str]] = {'left': None, 'right': None}

        # Callbacks
        self.on_gesture: Optional[Callable[[DetectedGesture], None]] = None
        self.on_landmarks: Optional[Callable[[List[HandLandmarks]], None]] = None

    async def start(self) -> bool:
        """Start the gesture processor."""
        if not MEDIAPIPE_AVAILABLE:
            logger.error("[GestureProcessor] MediaPipe not available")
            return False

        try:
            # Initialize MediaPipe
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5
            )
            self.mp_drawing = mp.solutions.drawing_utils

            # Open camera
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.error(f"[GestureProcessor] Cannot open camera {self.camera_index}")
                return False

            self.running = True
            logger.info(f"[GestureProcessor] Started with camera {self.camera_index}")
            return True

        except Exception as e:
            logger.error(f"[GestureProcessor] Start failed: {e}")
            return False

    async def stop(self) -> None:
        """Stop the gesture processor."""
        self.running = False

        if self.cap:
            self.cap.release()
            self.cap = None

        if self.hands:
            self.hands.close()
            self.hands = None

        logger.info("[GestureProcessor] Stopped")

    def process_frame(self, frame=None) -> Tuple[List[HandLandmarks], Optional[DetectedGesture]]:
        """
        Process a single frame for hand tracking and gesture recognition.

        Args:
            frame: Optional BGR frame. If None, captures from camera.

        Returns:
            Tuple of (list of hand landmarks, detected gesture or None)
        """
        if not self.running or not self.hands:
            return [], None

        # Capture frame if not provided
        if frame is None:
            if not self.cap or not self.cap.isOpened():
                return [], None
            ret, frame = self.cap.read()
            if not ret:
                return [], None

        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Process with MediaPipe
        results = self.hands.process(rgb_frame)

        landmarks_list = []
        detected_gesture = None

        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                # Determine hand side (from camera perspective, so flipped for avatar)
                hand_label = handedness.classification[0].label
                is_left = hand_label == 'Left'
                confidence = handedness.classification[0].score

                # Extract landmarks
                landmarks = self._process_hand_landmarks(hand_landmarks, is_left, confidence)
                landmarks_list.append(landmarks)

                # Track motion for gesture detection
                hand_key = 'left' if is_left else 'right'
                self._update_hand_history(hand_key, landmarks.wrist_x, landmarks.wrist_y)

                # Detect gestures
                gesture = self._detect_gesture(hand_landmarks, hand_key, confidence)
                if gesture and (detected_gesture is None or gesture.confidence > detected_gesture.confidence):
                    detected_gesture = gesture

        # Fire callbacks
        if self.on_landmarks and landmarks_list:
            self.on_landmarks(landmarks_list)

        if self.on_gesture and detected_gesture:
            self.on_gesture(detected_gesture)

        return landmarks_list, detected_gesture

    def _process_hand_landmarks(self, hand_landmarks, is_left: bool, confidence: float) -> HandLandmarks:
        """Convert MediaPipe landmarks to our format."""
        # Wrist position
        wrist = hand_landmarks.landmark[0]  # WRIST

        # Calculate arm lift from wrist Y position
        # Lower Y = higher on screen = arm raised more
        arm_lift = self._map_wrist_to_arm_lift(wrist.y)

        # Calculate hand openness from finger positions
        hand_openness = self._calculate_hand_openness(hand_landmarks)

        return HandLandmarks(
            wrist_x=wrist.x,
            wrist_y=wrist.y,
            arm_lift=arm_lift,
            hand_openness=hand_openness,
            is_left_hand=is_left,
            confidence=confidence
        )

    def _map_wrist_to_arm_lift(self, wrist_y: float) -> float:
        """
        Map wrist Y position to arm lift value.

        wrist_y: 0 = top of frame, 1 = bottom of frame
        Returns: -1 to 5 (matching armLB/armRB param range)
        """
        # Typical range: 0.3 (high) to 0.9 (low)
        # Map to -1 to 5
        if wrist_y < 0.3:
            return 5.0
        elif wrist_y > 0.9:
            return -1.0
        else:
            # Linear interpolation
            t = (0.9 - wrist_y) / 0.6  # 0 at bottom, 1 at top
            return -1.0 + t * 6.0  # -1 to 5

    def _calculate_hand_openness(self, hand_landmarks) -> float:
        """
        Calculate how open the hand is (0=fist, 1=open palm).
        Based on finger tip to MCP joint distances.
        """
        # Finger tip indices
        tips = [4, 8, 12, 16, 20]  # Thumb, Index, Middle, Ring, Pinky tips
        mcps = [2, 5, 9, 13, 17]   # Corresponding MCP joints

        total_extension = 0
        for tip_idx, mcp_idx in zip(tips, mcps):
            tip = hand_landmarks.landmark[tip_idx]
            mcp = hand_landmarks.landmark[mcp_idx]

            # Distance from MCP to tip
            dist = ((tip.x - mcp.x) ** 2 + (tip.y - mcp.y) ** 2) ** 0.5
            total_extension += dist

        # Normalize (typical range 0.1 to 0.5)
        normalized = min(1.0, max(0.0, (total_extension - 0.15) / 0.35))
        return normalized

    def _update_hand_history(self, hand_key: str, x: float, y: float) -> None:
        """Track hand position history for motion detection."""
        now = time.time()
        self.hand_history[hand_key].append((x, y, now))

        # Trim old entries
        while len(self.hand_history[hand_key]) > self.history_max_length:
            self.hand_history[hand_key].pop(0)

    def _detect_gesture(self, hand_landmarks, hand_key: str, confidence: float) -> Optional[DetectedGesture]:
        """Detect gestures from hand landmarks and motion."""
        now = time.time()

        # Check for swipe gestures
        swipe = self._detect_swipe(hand_key)
        if swipe:
            if self._check_cooldown(swipe, now):
                return DetectedGesture(
                    gesture_type=swipe,
                    confidence=confidence,
                    timestamp=now,
                    hand_side=hand_key
                )

        # Check for thumbs up
        if self._is_thumbs_up(hand_landmarks):
            gesture_type = GestureType.THUMBS_UP
            if self._check_cooldown(gesture_type, now):
                return DetectedGesture(
                    gesture_type=gesture_type,
                    confidence=confidence * 0.9,
                    timestamp=now,
                    hand_side=hand_key
                )

        # Check for wave (oscillating motion)
        if self._detect_wave(hand_key):
            gesture_type = GestureType.WAVE
            if self._check_cooldown(gesture_type, now):
                self.wave_oscillation_count[hand_key] = 0  # Reset count
                return DetectedGesture(
                    gesture_type=gesture_type,
                    confidence=confidence * 0.85,
                    timestamp=now,
                    hand_side=hand_key
                )

        # Check for pointing
        if self._is_pointing(hand_landmarks):
            gesture_type = GestureType.POINT
            if self._check_cooldown(gesture_type, now):
                return DetectedGesture(
                    gesture_type=gesture_type,
                    confidence=confidence * 0.8,
                    timestamp=now,
                    hand_side=hand_key
                )

        return None

    def _check_cooldown(self, gesture_type: GestureType, now: float) -> bool:
        """Check if gesture is off cooldown."""
        last_time = self.last_gesture_time.get(gesture_type, 0)
        if now - last_time >= self.gesture_cooldown:
            self.last_gesture_time[gesture_type] = now
            return True
        return False

    def _detect_swipe(self, hand_key: str) -> Optional[GestureType]:
        """Detect horizontal swipe gestures from hand motion."""
        history = self.hand_history[hand_key]
        if len(history) < 3:
            return None

        # Calculate velocity over last few frames
        x_positions = [h[0] for h in history[-5:]]
        if len(x_positions) < 3:
            return None

        # Average velocity
        velocities = [x_positions[i+1] - x_positions[i] for i in range(len(x_positions)-1)]
        avg_velocity = sum(velocities) / len(velocities)

        if avg_velocity > self.swipe_velocity_threshold:
            return GestureType.SWIPE_RIGHT
        elif avg_velocity < -self.swipe_velocity_threshold:
            return GestureType.SWIPE_LEFT

        return None

    def _detect_wave(self, hand_key: str) -> bool:
        """Detect wave gesture from oscillating horizontal motion."""
        history = self.hand_history[hand_key]
        if len(history) < 5:
            return False

        # Check for direction changes
        x_positions = [h[0] for h in history[-8:]]
        if len(x_positions) < 4:
            return False

        # Detect oscillations
        current_direction = None
        oscillations = 0

        for i in range(1, len(x_positions)):
            diff = x_positions[i] - x_positions[i-1]
            if abs(diff) > 0.02:  # Minimum movement threshold
                new_direction = 'right' if diff > 0 else 'left'
                if current_direction and new_direction != current_direction:
                    oscillations += 1
                current_direction = new_direction

        # Track oscillation count across frames
        if oscillations > 0:
            self.wave_oscillation_count[hand_key] += oscillations

        # Require 3+ oscillations for wave
        return self.wave_oscillation_count[hand_key] >= 3

    def _is_thumbs_up(self, hand_landmarks) -> bool:
        """Check if hand is making thumbs up gesture."""
        # Thumb tip should be above thumb IP joint
        thumb_tip = hand_landmarks.landmark[4]
        thumb_ip = hand_landmarks.landmark[3]

        if thumb_tip.y >= thumb_ip.y:  # Thumb not pointing up
            return False

        # Other fingers should be curled (tips below PIPs)
        finger_tips = [8, 12, 16, 20]
        finger_pips = [6, 10, 14, 18]

        for tip_idx, pip_idx in zip(finger_tips, finger_pips):
            tip = hand_landmarks.landmark[tip_idx]
            pip = hand_landmarks.landmark[pip_idx]
            if tip.y < pip.y:  # Finger extended
                return False

        return True

    def _is_pointing(self, hand_landmarks) -> bool:
        """Check if hand is pointing (index extended, others curled)."""
        # Index tip should be extended
        index_tip = hand_landmarks.landmark[8]
        index_pip = hand_landmarks.landmark[6]

        if index_tip.y >= index_pip.y:  # Index not extended
            return False

        # Other fingers should be curled
        other_tips = [12, 16, 20]
        other_pips = [10, 14, 18]

        for tip_idx, pip_idx in zip(other_tips, other_pips):
            tip = hand_landmarks.landmark[tip_idx]
            pip = hand_landmarks.landmark[pip_idx]
            if tip.y < pip.y:  # Finger extended
                return False

        return True

    async def run_loop(self, fps: int = 30) -> None:
        """
        Run continuous processing loop.

        Args:
            fps: Target frames per second
        """
        frame_time = 1.0 / fps

        while self.running:
            start = time.time()

            landmarks, gesture = self.process_frame()

            # Sleep for remaining frame time
            elapsed = time.time() - start
            if elapsed < frame_time:
                await asyncio.sleep(frame_time - elapsed)

    def get_recent_gestures(self, seconds: float = 5.0) -> List[GestureType]:
        """Get list of gesture types detected in the last N seconds."""
        now = time.time()
        recent = []
        for gesture_type, timestamp in self.last_gesture_time.items():
            if now - timestamp <= seconds:
                recent.append(gesture_type)
        return recent


# Gesture to LLM context mapping
GESTURE_CONTEXT = {
    GestureType.SWIPE_RIGHT: "User gestured: next/forward",
    GestureType.SWIPE_LEFT: "User gestured: back/previous",
    GestureType.THUMBS_UP: "User gestured: approve/good",
    GestureType.THUMBS_DOWN: "User gestured: disapprove/bad",
    GestureType.WAVE: "User gestured: hello/attention",
    GestureType.POINT: "User gestured: pointing at something",
    GestureType.OPEN_PALM: "User gestured: stop/wait",
    GestureType.FIST: "User gestured: emphasis",
}


def get_gesture_context(gesture: DetectedGesture) -> str:
    """Convert a detected gesture to LLM context string."""
    return GESTURE_CONTEXT.get(gesture.gesture_type, f"User gestured: {gesture.gesture_type.value}")
