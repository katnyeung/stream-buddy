"""
Avatar Controller - Main 24fps orchestrator for avatar animation.

Runs as an asyncio task in the FastAPI process, coordinating all engines
and pushing parameter updates to Redis for browser consumption.
"""
import asyncio
import logging
import time
from typing import Dict, Optional, Callable, Any

from .redis_backbone import RedisBackbone
from .parameter_blender import ParameterBlender
from .engines import (
    IdleEngine,
    StateEngine,
    ActionEngine,
    LipSyncEngine,
    RandomnessEngine,
)
from .models.state import AvatarState
from .models.personality import PersonalityProfile, PERSONALITY_PRESETS
from .utils.action_parser import ActionParser

logger = logging.getLogger(__name__)


class AvatarController:
    """
    Main controller for server-side avatar animation.

    Runs a 24fps async loop that:
    1. Reads state from Redis
    2. Updates all engines
    3. Blends parameters
    4. Pushes results back to Redis
    """

    # Target frame rate (reduced to avoid Redis spam)
    TARGET_FPS = 2  # 2 frames per second
    FRAME_TIME = 1.0 / TARGET_FPS  # 0.5 seconds per frame

    def __init__(
        self,
        avatar_id: str = "buddy",
        personality: str = "neutral",
        on_params_update: Optional[Callable[[Dict[str, float]], Any]] = None
    ):
        """
        Initialize the avatar controller.

        Args:
            avatar_id: Unique identifier for this avatar
            personality: Personality preset name
            on_params_update: Optional callback when params are updated
        """
        self.avatar_id = avatar_id
        self._personality_name = personality

        # Redis backbone
        self.redis = RedisBackbone(avatar_id)

        # Parameter blender
        self.blender = ParameterBlender()

        # Engines
        self.idle_engine = IdleEngine()
        self.state_engine = StateEngine()
        self.action_engine = ActionEngine()
        self.lipsync_engine = LipSyncEngine()
        self.randomness_engine = RandomnessEngine()

        # Action parser for processing LLM output
        self.action_parser = ActionParser()

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._current_state = AvatarState.IDLE
        self._current_mood = "neutral"
        self._personality = PERSONALITY_PRESETS.get(personality, PERSONALITY_PRESETS["neutral"])

        # Timing
        self._last_time = 0.0
        self._frame_count = 0

        # Current parameters (cached for quick access)
        self._current_params: Dict[str, float] = {}

        # Callback
        self._on_params_update = on_params_update

        # Exclude mouthOpen from action engine (lipsync controls it)
        self.action_engine.exclude_param("mouthOpen")

    async def start(self) -> None:
        """Start the avatar controller loop."""
        if self._running:
            return

        # Connect to Redis
        await self.redis.connect()
        await self.redis.init_avatar(self._personality_name)

        # Start the loop
        self._running = True
        self._last_time = time.time()
        self._task = asyncio.create_task(self._animation_loop())

        logger.info(f"[AvatarController] Started for avatar '{self.avatar_id}'")

    async def stop(self) -> None:
        """Stop the avatar controller loop."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await self.redis.cleanup()
        await self.redis.disconnect()

        logger.info(f"[AvatarController] Stopped for avatar '{self.avatar_id}'")

    async def _animation_loop(self) -> None:
        """Main 24fps animation loop."""
        while self._running:
            frame_start = time.time()

            try:
                await self._update_frame()
            except Exception as e:
                logger.error(f"[AvatarController] Frame error: {e}")

            # Calculate sleep time to maintain target FPS
            elapsed = time.time() - frame_start
            sleep_time = max(0, self.FRAME_TIME - elapsed)

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            self._frame_count += 1

    async def _update_frame(self) -> None:
        """Update a single animation frame."""
        now = time.time()
        delta_time = now - self._last_time
        self._last_time = now

        # Read state from Redis
        self._current_state = await self.redis.get_state()
        self._current_mood = await self.redis.get_mood()
        self._personality = await self.redis.get_personality()
        lipsync_amp = await self.redis.get_lipsync_amplitude()

        # Set lip sync amplitude
        self.lipsync_engine.set_amplitude(lipsync_amp)

        # Process action queue from Redis
        await self._process_action_queue()

        # Update all engines
        idle_params = self.idle_engine.update(
            delta_time, self._current_state, self._current_mood,
            self._personality, self._current_params
        )
        state_params = self.state_engine.update(
            delta_time, self._current_state, self._current_mood,
            self._personality, self._current_params
        )
        action_params = self.action_engine.update(
            delta_time, self._current_state, self._current_mood,
            self._personality, self._current_params
        )
        lipsync_params = self.lipsync_engine.update(
            delta_time, self._current_state, self._current_mood,
            self._personality, self._current_params
        )
        random_params = self.randomness_engine.update(
            delta_time, self._current_state, self._current_mood,
            self._personality, self._current_params
        )

        # Check for triggered gestures from state/randomness engines
        triggered_gestures = []
        if state_params.get("_trigger_gesture"):
            triggered_gestures.append(state_params["_trigger_gesture"])
        if random_params.get("_trigger_gesture"):
            triggered_gestures.append(random_params["_trigger_gesture"])

        # Queue triggered gestures
        for gesture_name in triggered_gestures:
            self.action_engine.play_gesture(gesture_name)

        # Set blender layers
        self.blender.set_layer("idle", idle_params)
        self.blender.set_layer("state", state_params)
        self.blender.set_layer("action", action_params)
        self.blender.set_layer("lipsync", lipsync_params)
        self.blender.set_layer("randomness", random_params)

        # Blend all layers
        final_params = self.blender.blend()

        # Update cached params
        self._current_params = final_params

        # Push to Redis
        await self.redis.update_params(final_params)

        # Callback if registered
        if self._on_params_update:
            self._on_params_update(final_params)

    async def _process_action_queue(self) -> None:
        """Process actions from Redis queue."""
        while True:
            action = await self.redis.dequeue_action()
            if not action:
                break

            action_type = action.get("type", "")
            name = action.get("name", "")
            params = action.get("params", {})

            if action_type == "mood":
                self.action_engine.set_mood(
                    name,
                    params.get("intensity"),
                    params.get("duration")
                )
            elif action_type == "gesture":
                self.action_engine.play_gesture(
                    name,
                    params.get("intensity"),
                    params.get("duration")
                )
            elif action_type == "action":
                self.action_engine.execute_compound(name, params.get("intensity"))

    # === Public API ===

    async def set_state(self, state: AvatarState) -> None:
        """Set avatar state (idle, listening, speaking, thinking)."""
        await self.redis.set_state(state)

    async def set_mood(self, mood: str, intensity: float = 1.0) -> None:
        """Set avatar mood."""
        await self.redis.set_mood(mood)
        self.action_engine.set_mood(mood, intensity)

    async def queue_gesture(self, gesture_name: str, params: Optional[Dict] = None) -> None:
        """Queue a gesture for execution."""
        await self.redis.queue_action("gesture", gesture_name, params)

    async def queue_action(self, action_type: str, name: str, params: Optional[Dict] = None) -> None:
        """Queue any action type."""
        await self.redis.queue_action(action_type, name, params)

    async def set_lipsync_amplitude(self, amplitude: float) -> None:
        """Set lip sync amplitude from browser."""
        await self.redis.set_lipsync_amplitude(amplitude)

    async def set_personality(self, personality: str) -> None:
        """Change personality preset."""
        await self.redis.set_personality(personality)
        self._personality = PERSONALITY_PRESETS.get(personality, PERSONALITY_PRESETS["neutral"])

    def parse_and_queue_actions(self, text: str) -> str:
        """
        Parse action tags from text and queue them.

        Args:
            text: Text with embedded action tags like [mood:happy] [gesture:nod]

        Returns:
            Clean text with tags removed
        """
        result = self.action_parser.parse(text)

        for action in result["actions"]:
            self.action_engine.queue_action(
                action["type"],
                action["name"],
                action.get("params", {})
            )

        return result["clean_text"]

    async def queue_speech(self, text: str, audio_base64: Optional[str] = None) -> None:
        """Queue a TTS speech item."""
        await self.redis.queue_speech(text, audio_base64)

    async def get_next_speech(self) -> Optional[Dict[str, Any]]:
        """Get next speech item from queue."""
        return await self.redis.dequeue_speech()

    # === Properties ===

    @property
    def current_params(self) -> Dict[str, float]:
        """Get current parameter values."""
        return self._current_params.copy()

    @property
    def current_state(self) -> AvatarState:
        """Get current avatar state."""
        return self._current_state

    @property
    def current_mood(self) -> str:
        """Get current mood."""
        return self._current_mood

    @property
    def is_running(self) -> bool:
        """Check if controller is running."""
        return self._running

    @property
    def frame_count(self) -> int:
        """Get total frames processed."""
        return self._frame_count
