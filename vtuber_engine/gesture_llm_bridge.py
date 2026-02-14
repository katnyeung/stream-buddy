"""
Gesture LLM Bridge - Integrates gesture detection with LLM context.

Responsibilities:
1. Maintain recent gesture history
2. Generate context strings for LLM prompts
3. Map gestures to potential avatar responses
4. Handle gesture-triggered navigation

This bridge acts as an intermediary between the GestureProcessor
and the LLM brain, providing contextual information about user gestures.
"""
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable

from .gesture_processor import (
    GestureProcessor,
    GestureType,
    DetectedGesture,
    HandLandmarks,
    GESTURE_CONTEXT,
    MEDIAPIPE_AVAILABLE
)
from .redis_backbone import RedisBackbone

logger = logging.getLogger(__name__)


@dataclass
class GestureEvent:
    """A gesture event with timing and context."""
    gesture_type: GestureType
    context: str
    timestamp: float
    hand_side: str
    processed: bool = False


class GestureLLMBridge:
    """
    Bridge between gesture detection and LLM context injection.

    Usage:
        bridge = GestureLLMBridge(avatar_id='buddy')
        await bridge.start()

        # When generating LLM response:
        context = bridge.get_gesture_context()
        if context:
            prompt += f"\\n{context}"

        # Bridge automatically handles navigation gestures
    """

    def __init__(
        self,
        avatar_id: str = 'buddy',
        camera_index: int = 0,
        history_duration: float = 10.0,
        arm_tracking_enabled: bool = True
    ):
        """
        Initialize gesture-LLM bridge.

        Args:
            avatar_id: Avatar ID for Redis communication
            camera_index: Camera index for gesture processor
            history_duration: How long to keep gesture history (seconds)
            arm_tracking_enabled: Whether to send arm positions to avatar
        """
        self.avatar_id = avatar_id
        self.camera_index = camera_index
        self.history_duration = history_duration
        self.arm_tracking_enabled = arm_tracking_enabled

        # Components
        self.processor: Optional[GestureProcessor] = None
        self.redis: Optional[RedisBackbone] = None

        # Gesture history (recent gestures for LLM context)
        self.gesture_history: deque[GestureEvent] = deque(maxlen=20)

        # Arm tracking state
        self.last_arm_update = 0
        self.arm_update_interval = 1.0 / 30  # 30fps

        # Callbacks
        self.on_navigation: Optional[Callable[[str], None]] = None

        # Running state
        self.running = False
        self._process_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """Start the gesture-LLM bridge."""
        if not MEDIAPIPE_AVAILABLE:
            logger.warning("[GestureLLMBridge] MediaPipe not available, bridge disabled")
            return False

        try:
            # Initialize Redis
            self.redis = RedisBackbone(avatar_id=self.avatar_id)
            await self.redis.connect()

            # Initialize gesture processor
            self.processor = GestureProcessor(camera_index=self.camera_index)

            # Set up callbacks
            self.processor.on_gesture = self._on_gesture_detected
            if self.arm_tracking_enabled:
                self.processor.on_landmarks = self._on_landmarks

            # Start processor
            if not await self.processor.start():
                logger.error("[GestureLLMBridge] Failed to start gesture processor")
                return False

            # Start processing loop
            self.running = True
            self._process_task = asyncio.create_task(self._process_loop())

            logger.info("[GestureLLMBridge] Started")
            return True

        except Exception as e:
            logger.error(f"[GestureLLMBridge] Start failed: {e}")
            return False

    async def stop(self) -> None:
        """Stop the gesture-LLM bridge."""
        self.running = False

        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        if self.processor:
            await self.processor.stop()

        if self.redis:
            await self.redis.disconnect()

        logger.info("[GestureLLMBridge] Stopped")

    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self.running:
            try:
                # Process frame (blocking call that handles callbacks)
                self.processor.process_frame()

                # Clean old history
                self._clean_old_history()

                # Small sleep to prevent CPU spin
                await asyncio.sleep(0.016)  # ~60fps

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[GestureLLMBridge] Process error: {e}")
                await asyncio.sleep(0.1)

    def _on_gesture_detected(self, gesture: DetectedGesture) -> None:
        """Handle detected gesture."""
        context = GESTURE_CONTEXT.get(
            gesture.gesture_type,
            f"User gestured: {gesture.gesture_type.value}"
        )

        event = GestureEvent(
            gesture_type=gesture.gesture_type,
            context=context,
            timestamp=gesture.timestamp,
            hand_side=gesture.hand_side
        )

        self.gesture_history.append(event)
        logger.info(f"[GestureLLMBridge] Gesture detected: {gesture.gesture_type.value}")

        # Handle navigation gestures
        if gesture.gesture_type == GestureType.SWIPE_RIGHT:
            self._trigger_navigation('next')
        elif gesture.gesture_type == GestureType.SWIPE_LEFT:
            self._trigger_navigation('back')

    def _on_landmarks(self, landmarks: List[HandLandmarks]) -> None:
        """Handle hand landmarks for arm tracking."""
        now = time.time()
        if now - self.last_arm_update < self.arm_update_interval:
            return

        self.last_arm_update = now

        # Send arm positions to avatar via Redis
        if self.redis and landmarks:
            asyncio.create_task(self._send_arm_params(landmarks))

    async def _send_arm_params(self, landmarks: List[HandLandmarks]) -> None:
        """Send arm parameters to avatar."""
        for landmark in landmarks:
            # Map camera left/right to avatar left/right (mirrored)
            # Camera left = avatar right (viewer's perspective)
            if landmark.is_left_hand:
                # Camera left hand -> avatar's right arm
                await self.redis.publish_command({
                    "type": "gesture",
                    "name": "arm_track_right",
                    "params": {
                        "arm_lift": landmark.arm_lift,
                        "hand_openness": landmark.hand_openness
                    }
                })
            else:
                # Camera right hand -> avatar's left arm
                await self.redis.publish_command({
                    "type": "gesture",
                    "name": "arm_track_left",
                    "params": {
                        "arm_lift": landmark.arm_lift,
                        "hand_openness": landmark.hand_openness
                    }
                })

    def _trigger_navigation(self, direction: str) -> None:
        """Trigger navigation from gesture."""
        logger.info(f"[GestureLLMBridge] Navigation triggered: {direction}")

        # Fire callback
        if self.on_navigation:
            self.on_navigation(direction)

        # Publish to Redis
        if self.redis:
            asyncio.create_task(
                self.redis.publish_navigation(direction, source="camera_gesture")
            )

    def _clean_old_history(self) -> None:
        """Remove old gestures from history."""
        now = time.time()
        cutoff = now - self.history_duration

        while self.gesture_history and self.gesture_history[0].timestamp < cutoff:
            self.gesture_history.popleft()

    def get_gesture_context(self, mark_as_processed: bool = True) -> Optional[str]:
        """
        Get context string for recent unprocessed gestures.

        Args:
            mark_as_processed: Whether to mark gestures as processed

        Returns:
            Context string for LLM prompt, or None if no gestures
        """
        unprocessed = [g for g in self.gesture_history if not g.processed]

        if not unprocessed:
            return None

        # Build context string
        contexts = []
        for gesture in unprocessed:
            contexts.append(gesture.context)
            if mark_as_processed:
                gesture.processed = True

        if len(contexts) == 1:
            return f"[{contexts[0]}]"
        else:
            return "[" + "; ".join(contexts) + "]"

    def get_recent_gestures(self, seconds: float = 5.0) -> List[GestureEvent]:
        """Get list of gesture events from the last N seconds."""
        now = time.time()
        cutoff = now - seconds
        return [g for g in self.gesture_history if g.timestamp >= cutoff]

    def has_recent_gesture(self, gesture_type: GestureType, seconds: float = 5.0) -> bool:
        """Check if a specific gesture was detected recently."""
        now = time.time()
        cutoff = now - seconds
        return any(
            g.gesture_type == gesture_type and g.timestamp >= cutoff
            for g in self.gesture_history
        )

    def get_suggested_response(self, gesture: GestureEvent) -> Dict[str, Any]:
        """
        Get suggested avatar response for a gesture.

        Returns dict with optional mood, gesture, and speech suggestions.
        """
        suggestions = {
            GestureType.THUMBS_UP: {
                "mood": "happy",
                "gesture": "nod",
                "speech_hint": "acknowledge positive feedback"
            },
            GestureType.THUMBS_DOWN: {
                "mood": "concerned",
                "gesture": "nod_slow",
                "speech_hint": "acknowledge and address concern"
            },
            GestureType.WAVE: {
                "mood": "friendly",
                "gesture": "wave",
                "speech_hint": "greet the user"
            },
            GestureType.POINT: {
                "mood": "curious",
                "gesture": "look_right" if gesture.hand_side == "right" else "look_left",
                "speech_hint": "look at what user is pointing at"
            },
            GestureType.SWIPE_RIGHT: {
                "mood": "friendly",
                "gesture": "nav_next",
                "speech_hint": "move to next section"
            },
            GestureType.SWIPE_LEFT: {
                "mood": "friendly",
                "gesture": "nav_back",
                "speech_hint": "go back to previous section"
            }
        }

        return suggestions.get(gesture.gesture_type, {})


# Convenience function for getting gesture context in LLM prompts
async def get_gesture_context_for_llm(avatar_id: str = 'buddy') -> Optional[str]:
    """
    Get gesture context for LLM prompt.

    This is a standalone function that can be used when a bridge
    instance isn't available. It reads from Redis.

    Returns:
        Context string or None
    """
    try:
        redis = RedisBackbone(avatar_id=avatar_id)
        await redis.connect()

        # Read gesture input from Redis (if gesture processor is writing there)
        # This is a simpler approach when full bridge isn't running
        gesture_data = await redis._redis.get(f"vtuber:{avatar_id}:gesture_input")

        await redis.disconnect()

        if gesture_data:
            return f"[{gesture_data}]"
        return None

    except Exception as e:
        logger.error(f"[get_gesture_context_for_llm] Error: {e}")
        return None
