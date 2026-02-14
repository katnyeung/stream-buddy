# VTuber Redis Backbone Implementation Guide

## Overview

This guide implements a Redis-backed "nervous system" for a VTuber avatar, providing:
- **Single source of truth** for all avatar parameters
- **Layered animation system** (idle, state, action, lip sync)
- **Organic randomness** for lifelike movement
- **Server-authoritative control** (Python controls everything, browser just renders)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              PYTHON BACKEND                              │
│                                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
│  │   Idle     │  │   State    │  │  Action    │  │  Lip Sync  │         │
│  │  Engine    │  │  Engine    │  │  Engine    │  │  Engine    │         │
│  │            │  │            │  │            │  │            │         │
│  │ - Noise    │  │ - Listening│  │ - Gestures │  │ - Audio    │         │
│  │ - Breathing│  │ - Speaking │  │ - Emotions │  │   analysis │         │
│  │ - Blinks   │  │ - Thinking │  │ - Triggered│  │            │         │
│  │ - Fidgets  │  │ - Idle     │  │   actions  │  │            │         │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘         │
│        │               │               │               │                 │
│        └───────────────┴───────┬───────┴───────────────┘                 │
│                                │                                         │
│                       ┌────────▼────────┐                                │
│                       │    Blender      │                                │
│                       │  (combines all  │                                │
│                       │   layers)       │                                │
│                       └────────┬────────┘                                │
│                                │                                         │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │         REDIS           │
                    │                         │
                    │  vtuber:{id}:params     │ ← 60fps updates
                    │  vtuber:{id}:state      │ ← idle/listening/speaking
                    │  vtuber:{id}:mood       │ ← from LLM
                    │  vtuber:{id}:action_queue│ ← pending gestures
                    │  vtuber:{id}:speech_queue│ ← pending speech
                    │  vtuber:{id}:personality │ ← movement style
                    │                         │
                    └────────────┬────────────┘
                                 │
                          Pub/Sub │ WebSocket
                                 │
                    ┌────────────▼────────────┐
                    │        BROWSER          │
                    │                         │
                    │   Live2D Renderer       │
                    │   (dumb client -        │
                    │    just applies params) │
                    │                         │
                    └─────────────────────────┘
```

---

## Directory Structure

```
stream-buddy/
├── vtuber/
│   ├── __init__.py
│   ├── redis_backbone.py       # Redis connection and schema
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── idle_engine.py      # Breathing, noise, blinks, fidgets
│   │   ├── state_engine.py     # State-based behaviors  
│   │   ├── action_engine.py    # Gesture/action execution
│   │   ├── lipsync_engine.py   # Audio-driven lip sync
│   │   └── randomness.py       # Spontaneous actions
│   ├── blender.py              # Combines all engine outputs
│   ├── avatar_controller.py    # Main controller
│   ├── websocket_server.py     # FastAPI WebSocket
│   ├── models/
│   │   ├── params.py           # Parameter definitions
│   │   └── personality.py      # Personality presets
│   └── web/
│       ├── index.html          # Browser client
│       └── app.js              # Live2D renderer
└── ...
```

---

## Phase 1: Redis Schema

### Key Structure

```
vtuber:{id}:params          # Hash - current parameter values (60fps)
vtuber:{id}:state           # String - idle/listening/speaking/thinking
vtuber:{id}:mood            # String - current mood from LLM
vtuber:{id}:action_queue    # List - pending gestures (FIFO)
vtuber:{id}:speech_queue    # Stream - pending speech items
vtuber:{id}:config          # Hash - avatar configuration
vtuber:{id}:personality     # Hash - movement personality settings

# Pub/Sub channel
vtuber:{id}:updates         # Real-time updates for WebSocket
```

### Parameter Schema

```python
DEFAULT_PARAMS = {
    # Head (degrees, -30 to 30)
    "head_x": 0.0,      # Turn left/right
    "head_y": 0.0,      # Look up/down
    "head_z": 0.0,      # Tilt

    # Eyes (0-1.3)
    "eye_l_open": 1.0,
    "eye_r_open": 1.0,
    "eye_x": 0.0,       # -1 to 1
    "eye_y": 0.0,       # -1 to 1

    # Mouth
    "mouth_open": 0.0,  # 0-1
    "mouth_form": 0.0,  # -1 (frown) to 1 (smile)

    # Eyebrows (-1 to 1)
    "brow_l_y": 0.0,
    "brow_r_y": 0.0,

    # Body
    "body_x": 0.0,      # Lean left/right
    "body_y": 0.0,      # Breathing
    "body_z": 0.0,      # Lean forward/back

    # Meta
    "timestamp": 0.0,
}
```

### Personality Schema

```python
DEFAULT_PERSONALITY = {
    # Noise
    "noise_multiplier": 1.0,
    "head_noise_amplitude": 1.5,
    "eye_noise_amplitude": 2.0,

    # Breathing
    "breathing_speed": 1.0,
    "breathing_depth": 2.0,

    # Blinking
    "blink_rate_multiplier": 1.0,
    "double_blink_chance": 0.15,

    # Spontaneous actions
    "spontaneous_multiplier": 1.0,

    # Movement style
    "energy_level": 0.7,        # 0=calm, 1=energetic
    "action_intensity": 1.0,
}
```

---

## Phase 2: Redis Backbone Class

### File: `vtuber/redis_backbone.py`

Key methods to implement:

```python
class RedisBackbone:
    """Redis connection manager for avatar state"""
    
    async def connect(self)
    async def disconnect(self)
    
    # Avatar lifecycle
    async def init_avatar(avatar_id, config, personality)
    async def delete_avatar(avatar_id)
    
    # Parameters (60fps)
    async def get_params(avatar_id) -> dict
    async def update_params(avatar_id, params, publish=True)
    
    # State
    async def get_state(avatar_id) -> str
    async def set_state(avatar_id, state, publish=True)
    
    # Mood
    async def get_mood(avatar_id) -> str
    async def set_mood(avatar_id, mood, publish=True)
    
    # Action queue
    async def queue_action(avatar_id, action)
    async def get_next_action(avatar_id) -> Optional[ActionItem]
    
    # Speech queue
    async def queue_speech(avatar_id, speech)
    async def get_next_speech(avatar_id) -> Optional[SpeechItem]
    
    # Personality
    async def get_personality(avatar_id) -> dict
    async def update_personality(avatar_id, settings)
    
    # Pub/Sub
    async def subscribe(avatar_id)
    async def listen() -> AsyncIterator
```

---

## Phase 3: Engine Layer System

### Layer Priority (highest to lowest)

1. **Lip Sync** - mouth_open only, overrides when speaking
2. **Action** - gestures, triggered events (absolute)
3. **Mood** - emotion expressions (absolute)
4. **State** - listening/speaking behaviors (additive)
5. **Randomness** - spontaneous actions (additive)
6. **Idle** - breathing, noise, blinks (additive)

### Idle Engine

Provides constant organic movement:

```python
class IdleEngine:
    """Always-running organic movements"""
    
    def update(delta_time, state, mood) -> dict:
        params = {}
        
        # Breathing (sin wave)
        params["body_y"] = sin(time * 0.8) * breathing_depth
        
        # Noise (layered sin waves, never repeats)
        params["head_x"] = noise.get(time) * head_amplitude
        params["head_y"] = noise.get(time) * head_amplitude * 0.7
        # ... etc for all params
        
        # Blinking (random interval 2-6s)
        if time_to_blink:
            params["eye_l_open"] = blink_curve(progress)
            params["eye_r_open"] = blink_curve(progress)
        
        # Fidgets (random interval 8-20s)
        if time_to_fidget:
            apply_random_fidget()
        
        return params
```

### State Engine

State-dependent behaviors:

```python
class StateEngine:
    """Behaviors based on current state"""
    
    # IDLE: wandering gaze, relaxed
    # LISTENING: focused, occasional nods
    # SPEAKING: controlled, expressive
    # THINKING: look away, contemplative
    
    def update(delta_time, mood) -> dict:
        if state == "listening":
            # Nod occasionally (random probability)
            # Focused eye position
            # Slight lean forward
        elif state == "thinking":
            # Look away
            # Head tilt
            # Slower movement
        # ... etc
```

### Action Engine

Triggered gestures and expressions:

```python
class ActionEngine:
    """Executes gestures and mood expressions"""
    
    # Pre-defined gestures
    GESTURES = {
        "nod": keyframes for head_y movement,
        "shake": keyframes for head_x movement,
        "tilt": keyframes for head_z,
        "lean_in": keyframes for body_z,
        "surprise": keyframes for eyes, brows, mouth,
        # ... etc
    }
    
    # Mood expressions
    MOODS = {
        "neutral": {mouth_form: 0, eye_open: 1, brow: 0},
        "happy": {mouth_form: 0.6, eye_open: 0.85, brow: 0.2},
        "sad": {mouth_form: -0.4, eye_open: 0.7, brow: -0.3},
        # ... etc
    }
    
    def trigger_action(name)
    def set_mood(mood)
    def update(delta_time) -> dict
```

### Randomness Engine

Spontaneous human-like moments:

```python
class RandomnessEngine:
    """Unpredictable organic behaviors"""
    
    SPONTANEOUS_ACTIONS = [
        # (name, probability_per_second, cooldown, params, condition)
        ("glance_away", 0.03, 5s, {eye_x: ±0.5}, None),
        ("micro_smile", 0.015, 10s, {mouth_form: 0.3}, not_sad),
        ("head_adjust", 0.02, 8s, {head_z: ±6}, None),
        ("brow_flash", 0.01, 15s, {brow: 0.5}, None),
        ("weight_shift", 0.008, 15s, {body_x: ±2.5}, None),
        ("thinking_squint", 0.015, 12s, {eye_open: 0.7}, listening),
        # ... etc
    ]
    
    def update(delta_time, state, mood) -> Optional[dict]:
        for action in actions:
            if random() < probability * delta_time:
                if cooldown_ok and condition_met:
                    trigger_action()
```

---

## Phase 4: Parameter Blender

Combines all engine outputs:

```python
class ParameterBlender:
    """Blends all layers into final parameters"""
    
    def add_layer(name, params, weight=1.0, additive=True)
    
    def blend() -> dict:
        result = base_params.copy()
        
        for layer in order:  # idle, state, randomness, mood, action, lipsync
            if layer.additive:
                result[param] += layer.value * weight
            else:
                result[param] = blend_toward(target, weight)
        
        return clamp_all(result)
```

---

## Phase 5: Main Avatar Controller

Orchestrates everything:

```python
class AvatarController:
    """Main controller running at 60fps"""
    
    async def start():
        connect_redis()
        init_avatar()
        load_personality()
        init_engines()
        start_main_loop()
    
    async def _main_loop():
        while running:
            delta_time = calculate_delta()
            
            # Get state from Redis
            state = await redis.get_state()
            mood = await redis.get_mood()
            
            # Process action queue
            await process_queued_actions()
            
            # Update all engines
            idle_params = idle_engine.update(delta_time, state, mood)
            state_params = state_engine.update(delta_time, mood)
            random_params = randomness_engine.update(delta_time, state, mood)
            action_params = action_engine.update(delta_time)
            
            # Blend
            blender.add_layer("idle", idle_params)
            blender.add_layer("state", state_params)
            # ... etc
            
            final_params = blender.blend()
            
            # Push to Redis
            await redis.update_params(final_params)
            
            await sleep(frame_time)
    
    # Public API
    async def set_state(state)
    async def set_mood(mood)
    async def trigger_gesture(gesture)
    async def speak(text, emotion, gestures, audio_url)
    def update_lipsync(amplitude, delta_time)
```

---

## Phase 6: WebSocket Server

Real-time browser communication:

```python
# FastAPI WebSocket endpoint

@app.websocket("/ws/avatar/{avatar_id}")
async def avatar_websocket(websocket, avatar_id):
    await manager.connect(websocket, avatar_id)
    
    # Subscribe to Redis updates
    # Forward to browser
    
    # Receive lip sync amplitude from browser
    # Forward to controller
```

---

## Phase 7: Browser Client

Dumb renderer - just applies parameters:

```javascript
class VTuberClient {
    // Load Live2D model with auto-behaviors DISABLED
    
    // WebSocket receives params at 60fps
    
    applyParams(params) {
        for (param, value) of params:
            live2d.setParameter(PARAM_MAP[param], value)
    }
    
    // Send audio amplitude for lip sync
    sendLipSyncAmplitude(amplitude)
}
```

---

## Implementation Order

```
Week 1:
├── Day 1-2: Redis backbone (connect, params, state, mood)
├── Day 3-4: Idle engine (breathing, noise, blinks)
├── Day 5: State engine (listening, speaking behaviors)

Week 2:
├── Day 1-2: Action engine (gestures, mood expressions)
├── Day 3: Randomness engine (spontaneous actions)
├── Day 4: Blender (combine all layers)
├── Day 5: Avatar controller (main loop)

Week 3:
├── Day 1-2: WebSocket server
├── Day 3-4: Browser client (Live2D renderer)
├── Day 5: Integration with Stream Buddy
```

---

## Integration with Stream Buddy

```python
# In your STT/LLM/TTS pipeline:

class StreamBuddyWithAvatar:
    def __init__(self):
        self.avatar = AvatarController(avatar_id="buddy")
    
    async def on_user_speaking(self):
        await self.avatar.set_state("listening")
    
    async def on_user_stopped(self):
        await self.avatar.set_state("thinking")
    
    async def on_llm_response(self, text, emotion, gestures):
        await self.avatar.speak(text, emotion, gestures)
        await self.avatar.set_state("speaking")
    
    async def on_tts_complete(self):
        await self.avatar.set_state("idle")
    
    def on_audio_frame(self, amplitude):
        self.avatar.update_lipsync(amplitude, delta_time)
```

---

## Key Principles

1. **Redis is the single source of truth**
   - All state lives in Redis
   - Browser just renders what Redis says
   - Easy to debug: `redis-cli HGETALL vtuber:buddy:params`

2. **Python controls everything**
   - All animation logic in Python
   - Browser is a "dumb" renderer
   - Disable all Live2D auto-behaviors

3. **Layered animation**
   - Each engine contributes to final pose
   - Layers blend together with weights
   - Higher priority layers can override

4. **Organic randomness**
   - Never perfectly still (noise)
   - Never perfectly predictable (random intervals)
   - Personality affects movement style

5. **State machine for behavior**
   - Clear states: idle, listening, speaking, thinking
   - Each state has distinct characteristics
   - Smooth transitions between states
