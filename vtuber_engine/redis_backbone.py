"""
Redis Backbone - Hybrid Architecture Command Channel.

This is a simplified Redis backbone for the hybrid VTuber architecture where:
- Backend sends COMMANDS via Redis Pub/Sub (mood, gesture, state, speech, movement)
- Frontend handles smooth 60fps animations locally

Redis Schema (simplified):
    vtuber:{id}:commands       # Pub/Sub channel - real-time command stream
    vtuber:{id}:state          # String - current state (for reconnection sync)
    vtuber:{id}:mood           # String - current mood (for reconnection sync)
    vtuber:{id}:gesture_queue  # List - pending gestures from external sources
    vtuber:{id}:lipsync        # String - current amplitude from browser
    vtuber:{id}:position       # Hash - current position state (x, y, scale, facing, zone, rotation)
    vtuber:{id}:navigation     # Pub/Sub channel - navigation triggers from gestures
"""
import asyncio
import json
import logging
import os
from typing import Dict, Optional, Any, AsyncGenerator

import redis.asyncio as redis

from .models.state import AvatarState

logger = logging.getLogger(__name__)


class RedisBackbone:
    """
    Simplified Redis backbone for hybrid VTuber architecture.
    Redis acts as a command channel, not a parameter store.
    """

    def __init__(self, avatar_id: str = "buddy"):
        """
        Initialize Redis backbone for a specific avatar.

        Args:
            avatar_id: Unique identifier for this avatar instance
        """
        self.avatar_id = avatar_id
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._prefix = f"vtuber:{avatar_id}"

    # === Key Properties ===

    @property
    def _commands_channel(self) -> str:
        """Pub/Sub channel for real-time commands."""
        return f"{self._prefix}:commands"

    @property
    def _state_key(self) -> str:
        """Current state (for reconnection sync)."""
        return f"{self._prefix}:state"

    @property
    def _mood_key(self) -> str:
        """Current mood (for reconnection sync)."""
        return f"{self._prefix}:mood"

    @property
    def _gesture_queue_key(self) -> str:
        """Pending gestures from external sources."""
        return f"{self._prefix}:gesture_queue"

    @property
    def _lipsync_key(self) -> str:
        """Current lip sync amplitude from browser."""
        return f"{self._prefix}:lipsync"

    @property
    def _position_key(self) -> str:
        """Current position state (for LLM awareness and reconnection sync)."""
        return f"{self._prefix}:position"

    @property
    def _navigation_channel(self) -> str:
        """Pub/Sub channel for navigation triggers."""
        return f"{self._prefix}:navigation"

    # === Connection ===

    async def connect(self) -> None:
        """Connect to Redis."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis = redis.from_url(redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info(f"[RedisBackbone] Connected for avatar '{self.avatar_id}'")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        if self._redis:
            await self._redis.close()
            self._redis = None

        logger.info(f"[RedisBackbone] Disconnected")

    async def init_avatar(self) -> None:
        """Initialize avatar state in Redis with defaults."""
        if not self._redis:
            await self.connect()

        # Set default state
        await self._redis.set(self._state_key, AvatarState.IDLE.value)
        await self._redis.set(self._mood_key, "neutral")
        await self._redis.set(self._lipsync_key, "0.0")

        # Set default position
        await self.set_position(self._default_position())

        # Clear gesture queue
        await self._redis.delete(self._gesture_queue_key)

        logger.info(f"[RedisBackbone] Avatar '{self.avatar_id}' initialized")

    async def cleanup(self) -> None:
        """Remove all avatar keys from Redis."""
        if not self._redis:
            return

        keys = [
            self._state_key,
            self._mood_key,
            self._gesture_queue_key,
            self._lipsync_key,
            self._position_key
        ]
        await self._redis.delete(*keys)
        logger.info(f"[RedisBackbone] Avatar '{self.avatar_id}' cleaned up")

    # === Command Publishing ===

    async def publish_command(self, command: dict) -> None:
        """
        Publish a command to the browser via Pub/Sub.

        Args:
            command: Command dict with 'type' and payload
                     e.g., {"type": "mood", "name": "happy", "intensity": 1.0}
        """
        if not self._redis:
            logger.warning(f"[RedisBackbone] Cannot publish {command.get('type')} - no Redis connection")
            return

        await self._redis.publish(self._commands_channel, json.dumps(command))
        cmd_type = command.get('type')
        # Log speech commands at INFO level for debugging
        if cmd_type == 'speech':
            text_preview = command.get('text', '')[:30]
            has_audio = 'yes' if command.get('audio_base64') else 'no'
            logger.info(f"[RedisBackbone] Published speech: '{text_preview}...' (audio: {has_audio})")
        else:
            logger.debug(f"[RedisBackbone] Published command: {cmd_type}")

    # === State ===

    async def get_state(self) -> AvatarState:
        """Get current avatar state."""
        if not self._redis:
            return AvatarState.IDLE

        state_str = await self._redis.get(self._state_key)
        try:
            return AvatarState(state_str) if state_str else AvatarState.IDLE
        except ValueError:
            return AvatarState.IDLE

    async def set_state(self, state: AvatarState) -> None:
        """Set avatar state and publish command."""
        if not self._redis:
            return

        await self._redis.set(self._state_key, state.value)

        # Publish state command
        await self.publish_command({
            "type": "state",
            "value": state.value
        })

        logger.debug(f"[RedisBackbone] State set to: {state.value}")

    # === Mood ===

    async def get_mood(self) -> str:
        """Get current mood."""
        if not self._redis:
            return "neutral"

        mood = await self._redis.get(self._mood_key)
        return mood if mood else "neutral"

    async def set_mood(self, mood: str, intensity: float = 1.0) -> None:
        """Set current mood and publish command."""
        if not self._redis:
            return

        mood_lower = mood.lower()
        await self._redis.set(self._mood_key, mood_lower)

        # Publish mood command
        await self.publish_command({
            "type": "mood",
            "name": mood_lower,
            "intensity": intensity
        })

        logger.debug(f"[RedisBackbone] Mood set to: {mood_lower}")

    # === Gesture Queue ===

    async def queue_gesture(self, gesture: str, source: str = "llm", intensity: float = 1.0) -> None:
        """
        Queue a gesture for the avatar.

        Args:
            gesture: Gesture name (e.g., "nod", "wave")
            source: Source of the gesture (llm, webcam, manual)
            intensity: Gesture intensity (0-1)
        """
        if not self._redis:
            return

        gesture_data = {
            "name": gesture.lower(),
            "source": source,
            "intensity": intensity
        }
        await self._redis.rpush(self._gesture_queue_key, json.dumps(gesture_data))

        # Also publish as command for immediate execution
        await self.publish_command({
            "type": "gesture",
            "name": gesture.lower(),
            "intensity": intensity,
            "source": source
        })

        logger.debug(f"[RedisBackbone] Queued gesture: {gesture} from {source}")

    async def dequeue_gesture(self) -> Optional[Dict[str, Any]]:
        """Get and remove the next gesture from the queue."""
        if not self._redis:
            return None

        raw = await self._redis.lpop(self._gesture_queue_key)
        if raw:
            return json.loads(raw)
        return None

    async def get_gesture_queue_length(self) -> int:
        """Get number of pending gestures."""
        if not self._redis:
            return 0
        return await self._redis.llen(self._gesture_queue_key)

    # === Action Command ===

    async def send_action(self, action_name: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Send a composite action command.

        Args:
            action_name: Name of the action (e.g., "greet_excited", "explain")
            params: Optional parameters for the action
        """
        await self.publish_command({
            "type": "action",
            "name": action_name.lower(),
            "params": params or {}
        })

        logger.debug(f"[RedisBackbone] Sent action: {action_name}")

    # === Speech Command ===

    async def send_speech(self, text: str, audio_base64: Optional[str] = None) -> None:
        """
        Send a speech command to trigger TTS playback.

        Args:
            text: Text being spoken
            audio_base64: Pre-generated audio in base64
        """
        logger.info(f"[RedisBackbone] send_speech called: '{text[:30]}...' (has_audio: {audio_base64 is not None})")
        await self.publish_command({
            "type": "speech",
            "text": text,
            "audio_base64": audio_base64
        })

    # === Lip Sync ===

    async def get_lipsync_amplitude(self) -> float:
        """Get current lip sync amplitude (0-1)."""
        if not self._redis:
            return 0.0

        amp = await self._redis.get(self._lipsync_key)
        return float(amp) if amp else 0.0

    async def set_lipsync_amplitude(self, amplitude: float) -> None:
        """Set current lip sync amplitude from browser."""
        if not self._redis:
            return
        await self._redis.set(self._lipsync_key, str(max(0.0, min(1.0, amplitude))))

    # === Position State ===

    async def get_position(self) -> Dict[str, Any]:
        """Get current position state."""
        if not self._redis:
            return self._default_position()

        pos_data = await self._redis.hgetall(self._position_key)
        if not pos_data:
            return self._default_position()

        return {
            "x": float(pos_data.get("x", 960)),
            "y": float(pos_data.get("y", 810)),
            "scale": float(pos_data.get("scale", 0.4)),
            "facing": pos_data.get("facing", "right"),
            "bodyOrientation": pos_data.get("bodyOrientation", "front")
        }

    def _default_position(self) -> Dict[str, Any]:
        """Return default position state."""
        return {
            "x": 960,
            "y": 810,
            "scale": 0.4,
            "facing": "right",
            "bodyOrientation": "front"
        }

    async def set_position(self, position: Dict[str, Any]) -> None:
        """Set position state (persisted for LLM awareness)."""
        if not self._redis:
            return

        await self._redis.hset(self._position_key, mapping={
            "x": str(position.get("x", 960)),
            "y": str(position.get("y", 810)),
            "scale": str(position.get("scale", 0.4)),
            "facing": position.get("facing", "right"),
            "bodyOrientation": position.get("bodyOrientation", "front")
        })

        logger.debug(f"[RedisBackbone] Position updated: x={position.get('x')}, y={position.get('y')}")

    async def update_position_field(self, field: str, value: Any) -> None:
        """Update a single position field."""
        if not self._redis:
            return
        await self._redis.hset(self._position_key, field, str(value))

    # === Movement Commands ===

    async def send_move(self, direction: str, duration: int = 400) -> None:
        """
        Send directional move command to browser.

        Args:
            direction: Direction (up, down, left, right)
            duration: Animation duration in ms
        """
        await self.publish_command({
            "type": "move",
            "direction": direction,
            "duration": duration
        })
        logger.debug(f"[RedisBackbone] Sent move: {direction}")

    async def send_move_to(self, x: float, y: float, duration: int = 600) -> None:
        """
        Send absolute position move command to browser.

        Args:
            x: Target X position (0-1 ratio or pixels)
            y: Target Y position (0-1 ratio or pixels)
            duration: Animation duration in ms
        """
        await self.publish_command({
            "type": "move_to",
            "x": x,
            "y": y,
            "duration": duration
        })
        logger.debug(f"[RedisBackbone] Sent move_to: ({x}, {y})")

    async def send_zoom(self, level: str, duration: int = 800) -> None:
        """
        Send zoom command to browser.

        Args:
            level: Zoom level (normal, in, out)
            duration: Animation duration in ms
        """
        await self.publish_command({
            "type": "zoom",
            "level": level,
            "duration": duration
        })
        logger.debug(f"[RedisBackbone] Sent zoom to {level}")

    async def send_body_orientation(self, direction: str) -> None:
        """
        Send body orientation command to browser.

        Args:
            direction: Body orientation (front, left, right)
        """
        await self.publish_command({
            "type": "body",
            "direction": direction
        })
        logger.debug(f"[RedisBackbone] Sent body orientation: {direction}")

    # === Navigation Triggers ===

    async def publish_navigation(self, direction: str, source: str = "gesture") -> None:
        """
        Publish navigation trigger for script advancement.

        Args:
            direction: Navigation direction (next, back)
            source: Source of the trigger (gesture, llm, manual)
        """
        if not self._redis:
            return

        await self._redis.publish(self._navigation_channel, json.dumps({
            "direction": direction,
            "source": source,
            "timestamp": asyncio.get_event_loop().time()
        }))
        logger.debug(f"[RedisBackbone] Navigation trigger: {direction} from {source}")

    async def subscribe_navigation(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to navigation triggers."""
        if not self._redis:
            return

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._navigation_channel)

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except json.JSONDecodeError:
                    continue

    # === Get Current State (for reconnection sync) ===

    async def get_current_state(self) -> Dict[str, Any]:
        """
        Get all current state for reconnection sync.

        Returns:
            Dict with state, mood, pending gestures count, and position
        """
        state = await self.get_state()
        mood = await self.get_mood()
        gesture_count = await self.get_gesture_queue_length()
        position = await self.get_position()

        return {
            "state": state.value,
            "mood": mood,
            "pending_gestures": gesture_count,
            "position": position
        }

    def get_position_context(self, position: Dict[str, Any]) -> str:
        """
        Generate position context string for LLM.

        Args:
            position: Position state dict

        Returns:
            Human-readable position context for LLM prompt
        """
        x = position.get("x", 960)
        y = position.get("y", 810)
        facing = position.get("facing", "right")
        body_orientation = position.get("bodyOrientation", "front")

        # Determine screen region from x position
        if x < 640:
            region = "left side"
        elif x > 1280:
            region = "right side"
        else:
            region = "center"

        context_parts = [f"position: {region}"]
        if facing != "right":
            context_parts.append(f"facing: {facing}")
        if body_orientation != "front":
            context_parts.append(f"body: {body_orientation}")

        return f"[Avatar position: {', '.join(context_parts)}]"

    # === Idle Processor Control ===

    async def start_idle_processor(self) -> None:
        """Send command to start the idle processor."""
        await self.publish_command({"type": "start_idle"})
        logger.debug(f"[RedisBackbone] Sent start_idle command")

    async def stop_idle_processor(self) -> None:
        """Send command to stop the idle processor."""
        await self.publish_command({"type": "stop_idle"})
        logger.debug(f"[RedisBackbone] Sent stop_idle command")

    # === Pub/Sub Subscription ===

    async def subscribe_commands(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to real-time command stream.

        Yields:
            Command dicts as they are published
        """
        if not self._redis:
            return

        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self._commands_channel)

        async for message in self._pubsub.listen():
            if message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except json.JSONDecodeError:
                    continue

    # === Overlay Commands ===

    async def send_overlay(
        self,
        overlay_type: str,
        options: Dict[str, Any],
        overlay_id: Optional[str] = None,
        animate_in: str = "fade"
    ) -> None:
        """
        Send overlay command to browser.

        Args:
            overlay_type: Type of overlay ('text', 'image', 'box')
            options: Overlay-specific options
            overlay_id: Unique ID for the overlay (auto-generated if not provided)
            animate_in: Animation type for showing overlay
        """
        import time
        await self.publish_command({
            "type": "overlay",
            "id": overlay_id or f"overlay_{int(time.time() * 1000)}",
            "overlay_type": overlay_type,
            "options": options,
            "animate_in": animate_in
        })
        logger.debug(f"[RedisBackbone] Sent overlay: {overlay_type}")

    async def hide_overlay(self, overlay_id: str, animate_out: str = "fade") -> None:
        """
        Hide a specific overlay.

        Args:
            overlay_id: ID of the overlay to hide
            animate_out: Animation type for hiding overlay
        """
        await self.publish_command({
            "type": "overlay_hide",
            "id": overlay_id,
            "animate_out": animate_out
        })
        logger.debug(f"[RedisBackbone] Hiding overlay: {overlay_id}")

    async def hide_all_overlays(self) -> None:
        """Hide all active overlays."""
        await self.publish_command({
            "type": "overlay_hide",
            "all": True
        })
        logger.debug("[RedisBackbone] Hiding all overlays")
