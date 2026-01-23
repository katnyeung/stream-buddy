"""
Redis Backbone - Hybrid Architecture Command Channel.

This is a simplified Redis backbone for the hybrid VTuber architecture where:
- Backend sends COMMANDS via Redis Pub/Sub (mood, gesture, state, speech)
- Frontend handles smooth 60fps animations locally

Redis Schema (simplified):
    vtuber:{id}:commands       # Pub/Sub channel - real-time command stream
    vtuber:{id}:state          # String - current state (for reconnection sync)
    vtuber:{id}:mood           # String - current mood (for reconnection sync)
    vtuber:{id}:gesture_queue  # List - pending gestures from external sources
    vtuber:{id}:lipsync        # String - current amplitude from browser
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
            self._lipsync_key
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
            return

        await self._redis.publish(self._commands_channel, json.dumps(command))
        logger.debug(f"[RedisBackbone] Published command: {command.get('type')}")

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
        await self.publish_command({
            "type": "speech",
            "text": text,
            "audio_base64": audio_base64
        })

        logger.debug(f"[RedisBackbone] Sent speech: '{text[:30]}...'")

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

    # === Get Current State (for reconnection sync) ===

    async def get_current_state(self) -> Dict[str, Any]:
        """
        Get all current state for reconnection sync.

        Returns:
            Dict with state, mood, and pending gestures count
        """
        state = await self.get_state()
        mood = await self.get_mood()
        gesture_count = await self.get_gesture_queue_length()

        return {
            "state": state.value,
            "mood": mood,
            "pending_gestures": gesture_count
        }

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
