"""
WebSocket Handler - Hybrid Architecture Command Forwarding.

This handler bridges Redis Pub/Sub commands to the browser via WebSocket.
The browser handles 60fps animations locally; we only send commands.

Strict Mode: Server sends random behaviors at 2fps (blinks, small movements).
Browser executes smoothly at 60fps via ActionExecutor.

Endpoints:
- /ws/avatar/{id} - Connect browser to receive commands

Protocol:
Server → Browser:
    {"type": "state", "value": "speaking"}
    {"type": "mood", "name": "happy", "intensity": 1.0}
    {"type": "gesture", "name": "nod", "intensity": 1.0}
    {"type": "action", "name": "greet_excited"}
    {"type": "speech", "text": "Hello!", "audio_base64": "..."}

Browser → Server:
    {"type": "lipsync", "amplitude": 0.65}
    {"type": "ready"}
    {"type": "gesture_complete", "name": "wave"}
"""
import asyncio
import json
import logging
import random
import time
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .redis_backbone import RedisBackbone
from .models.state import AvatarState

logger = logging.getLogger(__name__)

router = APIRouter()

# Active Redis connections by avatar ID
_redis_connections: Dict[str, RedisBackbone] = {}


# === Random Action Engine ===

class RandomActionEngine:
    """
    Generates random behaviors by sending gesture names to the browser.
    Browser handles smooth 60fps animation via ActionExecutor.

    Tick interval: 2 seconds (not 2fps)
    All intervals are randomized for natural feel.

    Uses gestures from ActionLibrary:
    - idle_sway, idle_breathe: Continuous idle movement (keyframe sequences)
    - blink: Periodic blinking (keyframe sequence)
    - head_turn_left/right: Big head turns (angleZ -30 to 30)
    - look_left, look_right, look_away: Glances
    - nod, tilt: State-specific gestures
    """

    def __init__(self):
        now = time.time()

        # All timers with randomized next intervals
        self.timers = {
            "blink": {"last": now, "next": self._rand(2.5, 5.5)},
            "idle_sway": {"last": now, "next": self._rand(3.0, 5.0)},
            "idle_breathe": {"last": now, "next": self._rand(2.5, 4.0)},
            "head_turn": {"last": now, "next": self._rand(8.0, 15.0)},  # Big head turn every 8-15s
        }

        self.last_gesture_time = {}  # Cooldowns for state-specific gestures

    def _rand(self, min_val: float, max_val: float) -> float:
        """Random interval between min and max."""
        return random.uniform(min_val, max_val)

    def _check_timer(self, name: str, min_interval: float, max_interval: float) -> bool:
        """Check if timer elapsed, reset with new random interval if so."""
        now = time.time()
        timer = self.timers[name]
        if now - timer["last"] >= timer["next"]:
            timer["last"] = now
            timer["next"] = self._rand(min_interval, max_interval)
            return True
        return False

    # State-specific random gestures and their chances per tick (every 2 seconds)
    STATE_GESTURES = {
        "idle": [
            ("tilt", 0.08),              # Occasional head tilt
            ("look_away", 0.05),         # Look away
            ("glance_left", 0.06),       # Quick glances
            ("glance_right", 0.06),
            ("sway", 0.04),              # Body sway
        ],
        "listening": [
            ("nod", 0.15),               # Attentive nods (frequent)
            ("nod_slow", 0.10),
            ("tilt", 0.08),
            ("lean_in", 0.05),           # Lean forward showing interest
        ],
        "speaking": [
            ("nod", 0.12),               # Emphasis nods
            ("tilt", 0.10),
            ("sway_talk", 0.08),         # Expressive body movement
            ("raise_brows", 0.06),       # Eyebrow emphasis
            ("glance_left", 0.05),
            ("glance_right", 0.05),
        ],
        "thinking": [
            ("look_away", 0.15),         # Looking away while thinking
            ("look_up", 0.12),           # Looking up thinking
            ("tilt", 0.10),
            ("ponder", 0.08),            # Pondering pose
            ("glance_left", 0.08),
            ("glance_right", 0.08),
        ],
    }

    def tick(self, state: str) -> List[Dict[str, Any]]:
        """
        Generate gesture commands for this tick (called every 2 seconds).
        Browser's ActionExecutor handles smooth 60fps animation.

        Args:
            state: Current avatar state (idle, listening, speaking, thinking)

        Returns:
            List of gesture commands to send
        """
        commands = []
        now = time.time()

        # === Continuous idle animations (randomized intervals) ===

        # Idle sway - gentle head/body movement (3-5 seconds)
        if self._check_timer("idle_sway", 3.0, 5.0):
            commands.append({
                "type": "gesture",
                "name": "idle_sway",
                "intensity": random.uniform(0.6, 1.0)
            })

        # Breathing - subtle body movement (2.5-4 seconds)
        if self._check_timer("idle_breathe", 2.5, 4.0):
            commands.append({
                "type": "gesture",
                "name": "idle_breathe",
                "intensity": random.uniform(0.7, 1.0)
            })

        # === Periodic blinks (2.5-5.5 seconds) ===
        if self._check_timer("blink", 2.5, 5.5):
            commands.append({
                "type": "gesture",
                "name": "blink",
                "intensity": 1.0
            })

        # === Big head turn (8-15 seconds) - angleZ -30 to 30 ===
        if self._check_timer("head_turn", 8.0, 15.0):
            # Randomly turn left or right
            turn_gesture = random.choice(["head_turn_left", "head_turn_right"])
            commands.append({
                "type": "gesture",
                "name": turn_gesture,
                "intensity": random.uniform(0.7, 1.0)
            })

        # === State-specific random gestures ===
        gestures = self.STATE_GESTURES.get(state, self.STATE_GESTURES["idle"])
        for gesture_name, chance in gestures:
            # Check cooldown (minimum 3 seconds between same gesture)
            last_time = self.last_gesture_time.get(gesture_name, 0)
            if now - last_time < 3.0:
                continue

            # Random chance per tick
            if random.random() < chance:
                commands.append({
                    "type": "gesture",
                    "name": gesture_name,
                    "intensity": random.uniform(0.5, 1.0)
                })
                self.last_gesture_time[gesture_name] = now
                # Only one random gesture per tick to avoid overwhelming
                break

        return commands


async def get_or_create_redis(avatar_id: str) -> RedisBackbone:
    """Get existing Redis connection or create new one."""
    if avatar_id not in _redis_connections:
        redis = RedisBackbone(avatar_id=avatar_id)
        await redis.connect()
        await redis.init_avatar()
        _redis_connections[avatar_id] = redis
    return _redis_connections[avatar_id]


async def remove_redis(avatar_id: str) -> None:
    """Disconnect and remove a Redis connection."""
    if avatar_id in _redis_connections:
        await _redis_connections[avatar_id].disconnect()
        del _redis_connections[avatar_id]


@router.websocket("/ws/avatar/{avatar_id}")
async def websocket_avatar(websocket: WebSocket, avatar_id: str):
    """
    WebSocket endpoint for avatar command streaming.

    The browser connects here to receive commands and sends lip sync back.
    Animation runs at 60fps in the browser; we send fire-and-forget commands.
    Server sends random behaviors at 2fps (strict mode).
    """
    await websocket.accept()
    logger.info(f"[WS Avatar] Client connected for avatar '{avatar_id}'")

    # Get or create Redis connection
    redis = await get_or_create_redis(avatar_id)

    # Track connection state
    connected = True

    # Random action engine for 2fps behaviors
    action_engine = RandomActionEngine()

    # Command forwarding task
    async def forward_commands():
        """Subscribe to Redis and forward commands to browser.
        Also handles start_idle/stop_idle commands to control idle processor.
        """
        nonlocal idle_running, random_action_task
        try:
            # Create a separate Redis connection for Pub/Sub
            sub_redis = RedisBackbone(avatar_id=avatar_id)
            await sub_redis.connect()

            async for command in sub_redis.subscribe_commands():
                if not connected:
                    break

                cmd_type = command.get("type", "")

                # Handle idle processor control commands (not forwarded to browser)
                if cmd_type == "start_idle":
                    if not idle_running:
                        idle_running = True
                        random_action_task = asyncio.create_task(send_random_actions())
                        logger.info(f"[WS Avatar] Idle processor started via Redis for '{avatar_id}'")
                    continue

                elif cmd_type == "stop_idle":
                    if idle_running and random_action_task is not None:
                        idle_running = False
                        random_action_task.cancel()
                        try:
                            await random_action_task
                        except asyncio.CancelledError:
                            pass
                        random_action_task = None
                        logger.info(f"[WS Avatar] Idle processor stopped via Redis for '{avatar_id}'")
                    continue

                # Forward other commands to browser
                try:
                    await websocket.send_json(command)
                    logger.debug(f"[WS Avatar] Forwarded: {cmd_type}")
                except Exception as e:
                    logger.warning(f"[WS Avatar] Send failed: {e}")
                    break

            await sub_redis.disconnect()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[WS Avatar] Forward error: {e}")

    # Periodic random action task (2fps = 500ms interval)
    async def send_random_actions():
        """Send random behaviors at 2fps based on current state."""
        try:
            while connected:
                # Get current state
                state = await redis.get_state()
                state_str = state.value if state else "idle"

                # Generate random actions
                actions = action_engine.tick(state_str)

                # Send each action
                for action in actions:
                    try:
                        await websocket.send_json(action)
                        logger.debug(f"[WS Avatar] Random: {action.get('name')}")
                    except Exception as e:
                        logger.warning(f"[WS Avatar] Random action send failed: {e}")
                        return

                # Wait 2 seconds per tick
                await asyncio.sleep(2.0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[WS Avatar] Random action error: {e}")

    # Start command forwarding task (always runs)
    forward_task = asyncio.create_task(forward_commands())

    # Idle processor task (starts on demand)
    random_action_task = None
    idle_running = False

    async def start_idle_processor():
        """Start the idle processor if not already running."""
        nonlocal random_action_task, idle_running
        if idle_running:
            return
        idle_running = True
        random_action_task = asyncio.create_task(send_random_actions())
        logger.info(f"[WS Avatar] Idle processor started for '{avatar_id}'")

    async def stop_idle_processor():
        """Stop the idle processor if running."""
        nonlocal random_action_task, idle_running
        if not idle_running or random_action_task is None:
            return
        idle_running = False
        random_action_task.cancel()
        try:
            await random_action_task
        except asyncio.CancelledError:
            pass
        random_action_task = None
        logger.info(f"[WS Avatar] Idle processor stopped for '{avatar_id}'")

    try:
        # Send initial state for sync
        current_state = await redis.get_current_state()
        await websocket.send_json({
            "type": "init",
            "avatar_id": avatar_id,
            "state": current_state["state"],
            "mood": current_state["mood"],
            "idle_running": idle_running
        })

        # Handle incoming messages from browser
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "lipsync":
                    # Browser sending lip sync amplitude
                    amplitude = float(data.get("amplitude", 0))
                    await redis.set_lipsync_amplitude(amplitude)

                elif msg_type == "ready":
                    # Browser ready for next speech/action
                    logger.debug(f"[WS Avatar] Browser ready")

                elif msg_type == "gesture_complete":
                    # Browser finished playing a gesture
                    gesture_name = data.get("name", "")
                    logger.debug(f"[WS Avatar] Gesture complete: {gesture_name}")

                elif msg_type == "set_state":
                    # Browser requesting state change (for testing)
                    state_str = data.get("state", "idle")
                    try:
                        state = AvatarState(state_str)
                        await redis.set_state(state)
                    except ValueError:
                        pass

                elif msg_type == "set_mood":
                    # Browser requesting mood change (for testing)
                    mood = data.get("mood", "neutral")
                    intensity = float(data.get("intensity", 1.0))
                    await redis.set_mood(mood, intensity)

                elif msg_type == "gesture":
                    # Browser requesting gesture (for testing)
                    name = data.get("name", "")
                    intensity = float(data.get("intensity", 1.0))
                    if name:
                        await redis.queue_gesture(name, source="manual", intensity=intensity)

                elif msg_type == "action":
                    # Browser requesting action (for testing)
                    name = data.get("name", "")
                    params = data.get("params", {})
                    if name:
                        await redis.send_action(name, params)

                elif msg_type == "start_idle":
                    # Start the idle processor (called when session starts)
                    await start_idle_processor()
                    await websocket.send_json({"type": "idle_started"})

                elif msg_type == "stop_idle":
                    # Stop the idle processor (called when session ends)
                    await stop_idle_processor()
                    await websocket.send_json({"type": "idle_stopped"})

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                logger.warning(f"[WS Avatar] Invalid JSON received")
            except Exception as e:
                logger.error(f"[WS Avatar] Message error: {e}")

    except WebSocketDisconnect:
        logger.info(f"[WS Avatar] Client disconnected from avatar '{avatar_id}'")
    except Exception as e:
        logger.error(f"[WS Avatar] Connection error: {e}")
    finally:
        connected = False
        idle_running = False

        # Cancel forward task
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

        # Cancel idle processor task if running
        if random_action_task is not None:
            random_action_task.cancel()
            try:
                await random_action_task
            except asyncio.CancelledError:
                pass

        logger.info(f"[WS Avatar] Cleanup complete for avatar '{avatar_id}'")


@router.websocket("/ws/avatar/{avatar_id}/subscribe")
async def websocket_subscribe(websocket: WebSocket, avatar_id: str):
    """
    Subscribe to avatar commands via Redis pub/sub.
    Alternative endpoint for read-only command monitoring.
    """
    await websocket.accept()
    logger.info(f"[WS Avatar Sub] Client subscribed to avatar '{avatar_id}'")

    redis = RedisBackbone(avatar_id)
    await redis.connect()

    try:
        async for command in redis.subscribe_commands():
            await websocket.send_json(command)

    except WebSocketDisconnect:
        logger.info(f"[WS Avatar Sub] Client unsubscribed from avatar '{avatar_id}'")
    except Exception as e:
        logger.error(f"[WS Avatar Sub] Error: {e}")
    finally:
        await redis.disconnect()


# === API Functions for External Use ===

async def send_state(avatar_id: str, state: str) -> None:
    """Send state command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    try:
        avatar_state = AvatarState(state)
        await redis.set_state(avatar_state)
    except ValueError:
        logger.warning(f"Invalid state: {state}")


async def send_mood(avatar_id: str, mood: str, intensity: float = 1.0) -> None:
    """Send mood command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.set_mood(mood, intensity)


async def send_gesture(avatar_id: str, gesture: str, intensity: float = 1.0, source: str = "api") -> None:
    """Send gesture command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.queue_gesture(gesture, source=source, intensity=intensity)


async def send_action(avatar_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> None:
    """Send action command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.send_action(action, params)


async def send_speech(avatar_id: str, text: str, audio_base64: Optional[str] = None) -> None:
    """Send speech command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.send_speech(text, audio_base64)
