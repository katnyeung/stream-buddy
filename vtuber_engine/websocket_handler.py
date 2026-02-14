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

    # Mood-specific gestures - these ADD to state gestures when mood is active
    MOOD_GESTURES = {
        "happy": [
            ("bounce", 0.15),            # Bouncy movement
            ("shrug", 0.10),             # Playful shrug
            ("nod", 0.12),               # Happy nods
            ("sway", 0.10),              # Swaying
        ],
        "excited": [
            ("bounce", 0.20),            # Very bouncy
            ("excited_hands", 0.12),     # Excited hand gestures
            ("nod_fast", 0.15),          # Fast nods
        ],
        "thinking": [
            ("look_away", 0.18),         # Looking away more
            ("eye_roll", 0.10),          # Thoughtful eye roll
            ("look_up", 0.15),           # Looking up
            ("ponder", 0.12),            # Pondering
            ("tilt_curious", 0.10),      # Curious tilt
        ],
        "curious": [
            ("raise_brows", 0.18),       # Raised eyebrows
            ("tilt_curious", 0.15),      # Curious head tilt
            ("lean_in", 0.12),           # Leaning forward
            ("raise_brow_left", 0.10),   # Single brow raise
        ],
        "surprised": [
            ("raise_brows", 0.20),       # Wide-eyed
            ("gasp", 0.08),              # Gasp
            ("lean_back", 0.12),         # Startle back
        ],
        "sad": [
            ("sigh", 0.15),              # Sighing
            ("look_down", 0.18),         # Looking down
            ("blink_slow", 0.12),        # Slow blinks
        ],
        "skeptical": [
            ("raise_brow_right", 0.18),  # Skeptical brow
            ("look_away", 0.15),         # Looking away
            ("tilt_right", 0.12),        # Skeptical tilt
        ],
        "annoyed": [
            ("eye_roll", 0.15),          # Eye roll
            ("sigh", 0.12),              # Sighing
            ("look_away", 0.12),         # Looking away
            ("furrow_brows", 0.12),      # Furrowed brows
        ],
        "amused": [
            ("laugh", 0.12),             # Light laugh
            ("tilt", 0.12),              # Amused tilt
            ("raise_brow_right", 0.10),  # Amused brow
        ],
        "confident": [
            ("nod", 0.15),               # Confident nods
            ("lean_back", 0.10),         # Relaxed posture
            ("sway", 0.08),              # Confident sway
        ],
        "concerned": [
            ("furrow_brows", 0.15),      # Worried brows
            ("tilt", 0.12),              # Concerned tilt
            ("lean_in", 0.12),           # Leaning in with concern
        ],
        "shy": [
            ("look_away", 0.20),         # Looking away
            ("glance_left", 0.15),       # Shy glances
            ("look_down", 0.15),         # Looking down
        ],
        "embarrassed": [
            ("look_away", 0.22),         # Avoiding eye contact
            ("look_down", 0.18),         # Looking down
            ("blink_slow", 0.12),        # Slow blinks
        ],
        "mischievous": [
            ("wink", 0.12),              # Playful wink
            ("tilt", 0.12),              # Mischievous tilt
            ("raise_brow_right", 0.15),  # Raised brow
            ("glance_right", 0.10),      # Glancing
        ],
        "sleepy": [
            ("blink_slow", 0.25),        # Slow blinks (frequent)
            ("look_down", 0.15),         # Droopy
            ("sigh", 0.10),              # Sleepy sighs
        ],
        "friendly": [
            ("nod", 0.15),               # Friendly nods
            ("tilt", 0.12),              # Warm tilt
            ("lean_in", 0.10),           # Friendly lean
        ],
        "serious": [
            ("nod_slow", 0.12),          # Deliberate nods
            ("furrow_brows", 0.10),      # Serious expression
        ],
        "determined": [
            ("nod", 0.15),               # Determined nods
            ("lean_in", 0.10),           # Focused lean
        ],
        "proud": [
            ("nod", 0.15),               # Proud nod
            ("lean_back", 0.12),         # Confident posture
            ("raise_brows", 0.08),       # Proud brows
        ],
    }

    def tick(self, state: str, mood: str = "neutral") -> List[Dict[str, Any]]:
        """
        Generate gesture commands for this tick (called every 2 seconds).
        Browser's ActionExecutor handles smooth 60fps animation.

        Args:
            state: Current avatar state (idle, listening, speaking, thinking)
            mood: Current avatar mood (happy, thinking, curious, etc.)

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

        # === Combine state and mood gestures ===
        # Get base state gestures
        all_gestures = list(self.STATE_GESTURES.get(state, self.STATE_GESTURES["idle"]))

        # Add mood-specific gestures with boosted chances
        mood_lower = mood.lower() if mood else "neutral"
        if mood_lower in self.MOOD_GESTURES:
            # Mood gestures get priority - add them with boosted weight
            mood_gestures = self.MOOD_GESTURES[mood_lower]
            all_gestures.extend(mood_gestures)

        # Shuffle to randomize which gesture gets picked first
        random.shuffle(all_gestures)

        for gesture_name, chance in all_gestures:
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

    async def safe_send_json(data: dict) -> bool:
        """Safely send JSON, returning False if connection is lost."""
        nonlocal connected
        if not connected:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception as e:
            if "not connected" in str(e).lower() or "disconnect" in str(e).lower():
                logger.debug(f"[WS Avatar] Connection lost during send")
                connected = False
                return False
            raise

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
                if not await safe_send_json(command):
                    break
                # Log speech commands at INFO level for debugging
                if cmd_type == 'speech':
                    text_preview = command.get('text', '')[:30]
                    has_audio = 'yes' if command.get('audio_base64') else 'no'
                    logger.info(f"[WS Avatar] Forwarded speech to browser: '{text_preview}...' (audio: {has_audio})")
                else:
                    logger.debug(f"[WS Avatar] Forwarded: {cmd_type}")

            await sub_redis.disconnect()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[WS Avatar] Forward error: {e}")

    # Periodic random action task (2fps = 500ms interval)
    async def send_random_actions():
        """Send random behaviors at 2fps based on current state and mood."""
        try:
            while connected:
                # Get current state and mood
                state = await redis.get_state()
                state_str = state.value if state else "idle"
                mood = await redis.get_mood()
                mood_str = mood if mood else "neutral"

                # Generate random actions (now mood-aware)
                actions = action_engine.tick(state_str, mood_str)

                # Send each action
                for action in actions:
                    if not await safe_send_json(action):
                        return
                    logger.debug(f"[WS Avatar] Random: {action.get('name')} (mood: {mood_str})")

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
        if not await safe_send_json({
            "type": "init",
            "avatar_id": avatar_id,
            "state": current_state["state"],
            "mood": current_state["mood"],
            "position": current_state.get("position"),
            "idle_running": idle_running
        }):
            logger.warning(f"[WS Avatar] Failed to send init state for '{avatar_id}'")
            return

        # Handle incoming messages from browser
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "lipsync":
                    # Control panel sending lip sync amplitude - broadcast to overlay
                    amplitude = float(data.get("amplitude", 0))
                    await redis.set_lipsync_amplitude(amplitude)
                    # Broadcast to all clients (overlay receives this)
                    await redis.publish_command({
                        "type": "lipsync",
                        "amplitude": amplitude
                    })

                elif msg_type == "lipsync_start":
                    # Control panel signals speech starting - broadcast to overlay
                    logger.info(f"[WS Avatar] Lip sync started for '{avatar_id}'")
                    await redis.publish_command({"type": "lipsync_start"})

                elif msg_type == "lipsync_end":
                    # Control panel signals speech ended - broadcast to overlay
                    await redis.publish_command({"type": "lipsync_end"})

                elif msg_type == "display_text":
                    # Control panel sending text for overlay display
                    text = data.get("text", "")
                    await redis.publish_command({
                        "type": "display_text",
                        "text": text
                    })

                elif msg_type == "clear_text":
                    # Control panel requesting overlay to clear text
                    await redis.publish_command({"type": "clear_text"})

                elif msg_type == "ready":
                    # Browser ready for next speech/action (audio queue empty)
                    logger.info(f"[WS Avatar] Browser ready (speech complete)")
                    # Broadcast speech_complete so control panel can resume VAD
                    await redis.publish_command({
                        "type": "speech_complete"
                    })
                    # Also set state back to idle
                    await redis.set_state(AvatarState.IDLE)

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
                    await safe_send_json({"type": "idle_started"})

                elif msg_type == "stop_idle":
                    # Stop the idle processor (called when session ends)
                    await stop_idle_processor()
                    await safe_send_json({"type": "idle_stopped"})

                elif msg_type == "movement_complete":
                    # Browser finished movement animation - update position state
                    position_data = {
                        "x": data.get("x", 960),
                        "y": data.get("y", 810),
                        "zone": data.get("zone", "center"),
                        "facing": data.get("facing", "right")
                    }
                    await redis.set_position(position_data)
                    logger.debug(f"[WS Avatar] Position updated: {position_data}")

                elif msg_type == "navigation_trigger":
                    # Browser triggered navigation (from nav gesture)
                    direction = data.get("direction", "next")
                    await redis.publish_navigation(direction, source="gesture")
                    logger.info(f"[WS Avatar] Navigation trigger: {direction}")

                elif msg_type == "move":
                    # Directional move command - forward via Redis
                    direction = data.get("direction", "")
                    duration = data.get("duration", 400)
                    await redis.publish_command({
                        "type": "move",
                        "direction": direction,
                        "duration": duration
                    })
                    logger.info(f"[WS Avatar] Move command: direction={direction}")

                elif msg_type == "move_to":
                    # Absolute position move - forward via Redis
                    x = data.get("x", 0.5)
                    y = data.get("y", 0.65)
                    duration = data.get("duration", 600)
                    await redis.publish_command({
                        "type": "move_to",
                        "x": x,
                        "y": y,
                        "duration": duration
                    })
                    logger.info(f"[WS Avatar] Move to: x={x}, y={y}")

                elif msg_type == "zoom":
                    # Zoom command - forward via Redis
                    level = data.get("level", "normal")
                    duration = data.get("duration", 800)
                    await redis.send_zoom(level, duration)
                    logger.info(f"[WS Avatar] Zoom command: level={level}")

                elif msg_type == "body":
                    # Body orientation command - forward via Redis
                    direction = data.get("direction", "front")
                    await redis.publish_command({
                        "type": "body",
                        "direction": direction
                    })
                    logger.info(f"[WS Avatar] Body orientation: direction={direction}")

                elif msg_type == "presentation_command":
                    # Presentation command from gesture recognition
                    command = data.get("command", "")
                    gesture = data.get("gesture", "")
                    hand = data.get("hand", "")

                    # Forward to Redis for script manager / LLM brain
                    await redis.publish_command({
                        "type": "presentation_command",
                        "command": command,
                        "gesture": gesture,
                        "hand": hand
                    })
                    logger.info(f"[WS Avatar] Presentation command: {command} (from {gesture})")

                elif msg_type == "position_update":
                    # Position update from browser (drag/zoom) - broadcast to all clients
                    position_data = {
                        "x": data.get("x", 960),
                        "y": data.get("y", 810),
                        "scale": data.get("scale", 0.4),
                    }
                    # Save to Redis state
                    await redis.set_position(position_data)
                    # Broadcast to all connected clients (control panel <-> overlay sync)
                    await redis.publish_command({
                        "type": "position_sync",
                        "x": position_data["x"],
                        "y": position_data["y"],
                        "scale": position_data["scale"],
                    })
                    logger.debug(f"[WS Avatar] Position broadcast: {position_data}")

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                logger.warning(f"[WS Avatar] Invalid JSON received")
            except Exception as e:
                # Suppress noisy "not connected" errors when connection is lost
                err_str = str(e).lower()
                if "not connected" in err_str or "disconnect" in err_str or "accept" in err_str:
                    logger.debug(f"[WS Avatar] Connection lost: {e}")
                    break
                logger.error(f"[WS Avatar] Message error: {e}")

    except WebSocketDisconnect:
        logger.info(f"[WS Avatar] Client disconnected from avatar '{avatar_id}'")
    except Exception as e:
        # Suppress noisy connection errors
        err_str = str(e).lower()
        if "not connected" in err_str or "disconnect" in err_str or "accept" in err_str:
            logger.debug(f"[WS Avatar] Connection closed: {e}")
        else:
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
    connected = True

    try:
        async for command in redis.subscribe_commands():
            if not connected:
                break
            try:
                await websocket.send_json(command)
            except Exception as e:
                if "not connected" in str(e).lower() or "disconnect" in str(e).lower():
                    connected = False
                    break
                raise

    except WebSocketDisconnect:
        logger.info(f"[WS Avatar Sub] Client unsubscribed from avatar '{avatar_id}'")
    except Exception as e:
        if "not connected" not in str(e).lower():
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


async def send_move(avatar_id: str, direction: str, duration: int = 400) -> None:
    """Send directional move command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.send_move(direction, duration)


async def send_move_to(avatar_id: str, x: float, y: float, duration: int = 600) -> None:
    """Send absolute position move command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.send_move_to(x, y, duration)


async def send_zoom(avatar_id: str, level: str, duration: int = 800) -> None:
    """Send zoom command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.send_zoom(level, duration)


async def send_body_orientation(avatar_id: str, direction: str) -> None:
    """Send body orientation command to an avatar."""
    redis = await get_or_create_redis(avatar_id)
    await redis.send_body_orientation(direction)


async def get_position(avatar_id: str) -> Dict[str, Any]:
    """Get current position state for an avatar."""
    redis = await get_or_create_redis(avatar_id)
    return await redis.get_position()


async def get_position_context(avatar_id: str) -> str:
    """Get position context string for LLM prompt."""
    redis = await get_or_create_redis(avatar_id)
    position = await redis.get_position()
    return redis.get_position_context(position)
