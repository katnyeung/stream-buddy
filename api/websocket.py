"""
WebSocket handler for real-time audio streaming.
Continuous loop: Listen -> Transcribe -> Brain decides -> Act
Similar to hospit-interview pattern.
"""
import json
import uuid
import time
import asyncio
import tempfile
import os
import re
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.audio_buffer import AudioBuffer
from core.stt_client import transcribe_audio
from core.tts_client import text_to_speech
from core.script_manager import parse_script, analyze_progress, get_current_prompt
from core.redis_client import clear_session, store_session_state, get_session_state

# VTuber engine integration (optional) - Hybrid architecture
try:
    from vtuber_engine.redis_backbone import RedisBackbone
    from vtuber_engine.models.state import AvatarState
    from vtuber_engine.utils.action_parser import ActionParser
    VTUBER_AVAILABLE = True
except ImportError:
    VTUBER_AVAILABLE = False
    RedisBackbone = None
    AvatarState = None
    ActionParser = None


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences for TTS queue, preserving action tags."""
    if not text:
        return []

    # Split on .!? followed by space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# Timing configs
MIN_AUDIO_BYTES = 50000  # Minimum audio to transcribe (~5s of speech)
MIN_WORDS_FOR_BRAIN = 5  # Minimum words to filter noise (pause-based trigger)
BRAIN_CALL_COOLDOWN = 0  # Disabled - frontend VAD already gates with pause detection

# Periodic transcription (transcribe even without pause, for faster feedback)
DEFAULT_PERIODIC_TRANSCRIBE_SECONDS = 5  # Transcribe every 5s of audio (0 = disabled, only VAD)

# Cooldowns by style (set dynamically)
COOLDOWNS = {
    "aggressive": {"enrich": 20000, "remind": 15000},  # 20s enrich, 15s remind
    "balanced": {"enrich": 45000, "remind": 30000},    # 45s enrich, 30s remind
    "passive": {"enrich": 120000, "remind": 60000}     # 2min enrich (rare), 1min remind
}
# Proactive mode cooldowns (overrides style when enabled)
PROACTIVE_COOLDOWNS = {"enrich": 10000, "remind": 8000}  # Very proactive - leads conversation
ENRICH_COOLDOWN_MS = 45000  # Default, overridden by style
REMIND_COOLDOWN_MS = 30000  # Default, overridden by style


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket, session: str = None):
    """Main WebSocket endpoint - continuous listening loop."""
    await websocket.accept()

    from main import load_config
    config = load_config()

    # Use client-provided session ID or generate new one
    session_id = session if session else str(uuid.uuid4())[:8]
    logger.info(f"[{session_id}] WebSocket connected (client_session={session is not None})")

    # Initialize components
    audio_buffer = AudioBuffer()
    voice = config.get("persona", {}).get("voice", "Rachel")
    whisper_context = config.get("whisper_context", "")

    # Session state
    script_loaded = False
    full_transcript = ""
    last_prompt = ""
    last_remind_time = 0  # Track visual reminders
    last_enrich_time = 0  # Track verbal enrichments
    is_speaking = False
    selected_voice = None  # User-selected TTS voice
    selected_style = "balanced"  # Co-host style: aggressive/balanced/passive/skeptical
    selected_personality = "neutral"  # Co-host personality: positive/neutral/critical
    proactive_mode = False  # Proactive mode: buddy leads conversation, starts first
    selected_tts_model = "eleven_flash_v2_5"  # TTS model: flash/turbo/multilingual
    session_start_time = None  # Track when presentation started
    target_duration_mins = 10  # Default target duration in minutes
    all_sections_covered = set()  # Track all sections covered so far
    conversation_timeline = []  # Track timestamped conversation: [{"time": "00:30", "speaker": "User", "text": "..."}]
    last_brain_call_time = 0  # Track last brain call for cooldown
    accumulated_transcript = ""  # Accumulate transcript between brain calls

    # Periodic transcription settings
    periodic_transcribe_seconds = DEFAULT_PERIODIC_TRANSCRIBE_SECONDS
    last_periodic_transcribe_time = 0  # Track last periodic transcription

    # Manual response mode (hotkey to trigger avatar speech)
    auto_response_enabled = True  # True = auto respond, False = wait for hotkey
    pending_response = None  # Store prepared response waiting for hotkey

    # Concurrent Brain processing
    brain_task = None  # Background task for Brain processing
    brain_processing = False  # Flag to prevent concurrent brain calls

    # Proactive mode: track if welcome just played (to auto-trigger follow-up)
    proactive_welcome_played = False

    # VTuber Redis backbone for hybrid mode (optional)
    avatar_redis = None
    avatar_action_parser = None
    if VTUBER_AVAILABLE:
        try:
            avatar_redis = RedisBackbone(avatar_id=session_id)
            avatar_action_parser = ActionParser()
            await avatar_redis.connect()
            await avatar_redis.init_avatar()
            logger.info(f"[{session_id}] VTuber Redis backbone connected (hybrid mode)")
        except Exception as e:
            logger.warning(f"[{session_id}] VTuber Redis connection failed: {e}")
            avatar_redis = None

    # Send ready
    await websocket.send_json({
        "type": "ready",
        "session_id": session_id,
        "persona_name": config.get("persona", {}).get("name", "Buddy")
    })

    try:
        # Main loop - continuous listening
        while True:
            try:
                # Receive with timeout for periodic processing
                data = await asyncio.wait_for(websocket.receive(), timeout=0.5)

                if "bytes" in data:
                    # Audio chunk received
                    audio_buffer.append(data["bytes"])

                    # Check for periodic transcription (runs even while receiving audio)
                    if (script_loaded and
                        not is_speaking and
                        periodic_transcribe_seconds > 0 and
                        audio_buffer.total_bytes >= MIN_AUDIO_BYTES):

                        now = time.time()
                        time_since_last = now - last_periodic_transcribe_time

                        if time_since_last >= periodic_transcribe_seconds:
                            logger.info(f"[{session_id}] Periodic transcribe ({audio_buffer.total_bytes} bytes, {time_since_last:.1f}s)")
                            last_periodic_transcribe_time = now

                            filepath = await audio_buffer.save_to_temp_file()
                            if filepath:
                                transcript = await transcribe_audio(filepath, whisper_context)

                                # Skip hallucinations (just punctuation or very short)
                                clean_transcript = transcript.strip() if transcript else ""
                                is_hallucination = len(clean_transcript) < 3 or clean_transcript.replace(".", "").replace(",", "").strip() == ""

                                if transcript and not is_hallucination:
                                    # Accumulate transcript
                                    accumulated_transcript += " " + transcript
                                    accumulated_transcript = accumulated_transcript.strip()

                                    # Add to timeline
                                    if session_start_time:
                                        elapsed_secs = now - session_start_time
                                        conversation_timeline.append({
                                            "time": format_timestamp(elapsed_secs),
                                            "speaker": "User",
                                            "text": transcript
                                        })
                                        if len(conversation_timeline) > 10:
                                            conversation_timeline.pop(0)

                                    # Send transcript to frontend (live feedback)
                                    await websocket.send_json({
                                        "type": "transcript",
                                        "text": transcript,
                                        "is_partial": True
                                    })

                                    logger.info(f"[{session_id}] Periodic STT: '{transcript[:40]}...' (accumulated: {len(accumulated_transcript.split())} words)")

                                # Clear buffer after periodic transcription to avoid duplicate with VAD
                                audio_buffer.clear_accumulator()

                elif "text" in data:
                    msg = json.loads(data["text"])
                    msg_type = msg.get("type", "")

                    if msg_type == "load_script":
                        # Parse script with Gemini
                        script_text = msg.get("script", "")
                        selected_voice = msg.get("voice")  # Get user-selected voice
                        selected_style = msg.get("style", "balanced")  # Get co-host style
                        selected_personality = msg.get("personality", "neutral")  # Get personality
                        selected_tts_model = msg.get("tts_model", "eleven_flash_v2_5")  # Get TTS model
                        proactive_mode = msg.get("proactive", False)  # Proactive mode: buddy leads conversation
                        if script_text:
                            logger.info(f"[{session_id}] Loading script, voice: {selected_voice}, style: {selected_style}, personality: {selected_personality}, tts: {selected_tts_model}, proactive: {proactive_mode}")
                            start = time.time()

                            structure = await parse_script(session_id, script_text)
                            script_loaded = True
                            total_sections = structure.get("total_sections", len(structure.get("sections", [])))
                            # Get target duration from parsed script (LLM extracts from script content)
                            target_duration_mins = structure.get("target_duration_mins", 10)

                            logger.info(f"[{session_id}] Script parsed in {time.time()-start:.2f}s, target: {target_duration_mins}min")

                            initial_prompt = await get_current_prompt(session_id)

                            await websocket.send_json({
                                "type": "script_loaded",
                                "structure": structure,
                                "initial_prompt": initial_prompt,
                                "target_duration": target_duration_mins
                            })

                    elif msg_type == "start_presentation":
                        # User clicked start - begin timer and send welcome greeting
                        session_start_time = time.time()
                        all_sections_covered = set()
                        is_speaking = True

                        # Start avatar idle processor
                        if avatar_redis:
                            await avatar_redis.start_idle_processor()
                            logger.info(f"[{session_id}] Avatar idle processor started")

                        # Get structure for welcome message
                        from core.redis_client import get_script_structure
                        structure = await get_script_structure(session_id)
                        total_sections = structure.get("total_sections", 1) if structure else 1
                        title = structure.get("title", "your presentation") if structure else "your presentation"

                        # Style-aware welcome messages
                        if proactive_mode:
                            # Get first section details for proactive kickoff
                            first_section_title = ""
                            first_section_point = ""
                            if structure and structure.get("sections"):
                                first_section = structure["sections"][0]
                                first_section_title = first_section.get("title", "the first topic")
                                # Get first key point for context
                                points = first_section.get("key_points", [])
                                if points:
                                    point = points[0]
                                    first_section_point = point.get("text", str(point)) if isinstance(point, dict) else str(point)

                            welcome_text = f"[mood:excited] [gesture:wave] Welcome everyone! I'm Buddy, your host today. [head:nod] We're diving into {title}, and I've got {total_sections} great topics lined up. [body:lean_in] Let's kick things off with our first section: {first_section_title}. [gesture:present] So tell me, what's the story here? What should our audience know about this?"
                        else:
                            welcome_text = f"Hi! I'm Buddy, your AI cohost. We have {target_duration_mins} minutes and {total_sections} sections to cover. Let's make this a great presentation! Go ahead and start whenever you're ready."

                        logger.info(f"[{session_id}] Starting presentation, sending welcome")

                        await websocket.send_json({
                            "type": "cohost_speaking",
                            "text": welcome_text,
                            "reason": "Welcome greeting"
                        })

                        tts_start = time.time()
                        audio_base64 = await text_to_speech(welcome_text, selected_voice, selected_tts_model)
                        logger.info(f"[{session_id}] Welcome TTS in {time.time()-tts_start:.2f}s")

                        await websocket.send_json({
                            "type": "cohost_audio",
                            "text": welcome_text,
                            "audio_base64": audio_base64
                        })

                        # Set avatar to speaking state (lip sync handled by control panel)
                        if avatar_redis:
                            await avatar_redis.set_state(AvatarState.SPEAKING)

                        # Mark that welcome was played (for proactive auto-follow-up)
                        if proactive_mode:
                            proactive_welcome_played = True

                    elif msg_type == "ready_for_audio":
                        is_speaking = False
                        # Clear any audio captured during TTS playback (echo)
                        audio_buffer.clear_all()
                        logger.info(f"[{session_id}] Ready for audio (TTS finished, buffer cleared)")

                        # Set avatar to idle state
                        if avatar_redis:
                            await avatar_redis.set_state(AvatarState.IDLE)

                        # Proactive mode: auto-trigger follow-up after welcome
                        if proactive_mode and proactive_welcome_played and script_loaded:
                            proactive_welcome_played = False  # Only trigger once
                            logger.info(f"[{session_id}] Proactive mode: auto-triggering follow-up question")

                            # Short delay then trigger brain with synthetic input
                            await asyncio.sleep(2.0)  # Brief pause after welcome

                            # Trigger brain with proactive kickoff context
                            elapsed_mins = (time.time() - session_start_time) / 60 if session_start_time else 0
                            supports_emotions = selected_tts_model == "eleven_multilingual_v2"

                            result = await analyze_progress(
                                session_id,
                                "[Host is ready, waiting for me to lead into the first topic]",
                                selected_style,
                                selected_personality,
                                supports_emotions,
                                elapsed_mins=elapsed_mins,
                                target_mins=target_duration_mins,
                                sections_done=list(all_sections_covered),
                                timeline=conversation_timeline,
                                proactive=proactive_mode
                            )

                            action = result.get("action", "wait")
                            speak_text = result.get("speak_text", "")

                            if action in ("respond", "enrich") and speak_text:
                                is_speaking = True
                                logger.info(f"[{session_id}] Proactive follow-up: '{speak_text[:60]}...'")

                                # Add to timeline
                                now = time.time()
                                elapsed_secs = now - session_start_time if session_start_time else 0
                                conversation_timeline.append({
                                    "time": format_timestamp(elapsed_secs),
                                    "speaker": "Buddy",
                                    "text": speak_text
                                })
                                if len(conversation_timeline) > 10:
                                    conversation_timeline.pop(0)

                                await websocket.send_json({
                                    "type": "cohost_speaking",
                                    "text": speak_text,
                                    "reason": "Proactive mode leading conversation"
                                })

                                # Split into sentences and queue TTS
                                sentences = split_into_sentences(speak_text)
                                if avatar_redis:
                                    await avatar_redis.set_state(AvatarState.SPEAKING)

                                for i, sentence in enumerate(sentences):
                                    audio_base64 = await text_to_speech(sentence, selected_voice, selected_tts_model)
                                    await websocket.send_json({
                                        "type": "cohost_audio_queued",
                                        "text": sentence,
                                        "audio_base64": audio_base64
                                    })

                    elif msg_type == "reset":
                        logger.info(f"[{session_id}] Resetting session")
                        # Stop avatar idle processor
                        if avatar_redis:
                            await avatar_redis.stop_idle_processor()
                        await clear_session(session_id)
                        script_loaded = False
                        full_transcript = ""
                        audio_buffer.clear_all()
                        last_prompt = ""
                        last_remind_time = 0
                        last_enrich_time = 0
                        pending_response = None
                        session_start_time = None
                        await websocket.send_json({"type": "reset_complete"})

                    elif msg_type == "set_auto_response":
                        # Toggle auto/manual response mode
                        auto_response_enabled = msg.get("enabled", True)
                        logger.info(f"[{session_id}] Auto response: {auto_response_enabled}")
                        await websocket.send_json({
                            "type": "auto_response_changed",
                            "enabled": auto_response_enabled
                        })

                    elif msg_type == "set_periodic_interval":
                        # Set periodic transcription interval (0 = disabled)
                        periodic_transcribe_seconds = msg.get("seconds", DEFAULT_PERIODIC_TRANSCRIBE_SECONDS)
                        logger.info(f"[{session_id}] Periodic transcribe interval: {periodic_transcribe_seconds}s")
                        await websocket.send_json({
                            "type": "periodic_interval_changed",
                            "seconds": periodic_transcribe_seconds
                        })

                    elif msg_type == "trigger_response":
                        # Manual hotkey pressed - speak the pending response
                        if pending_response:
                            logger.info(f"[{session_id}] Manual trigger - speaking pending response")
                            is_speaking = True
                            speak_text = pending_response["speak_text"]
                            result = pending_response["result"]

                            # Add to timeline
                            now = time.time()
                            elapsed_secs = now - session_start_time if session_start_time else 0
                            conversation_timeline.append({
                                "time": format_timestamp(elapsed_secs),
                                "speaker": "Buddy",
                                "text": speak_text
                            })
                            if len(conversation_timeline) > 10:
                                conversation_timeline.pop(0)

                            audio_buffer.clear_all()

                            # Send speaking notification
                            await websocket.send_json({
                                "type": "cohost_speaking",
                                "text": speak_text,
                                "reason": result.get("reason", "manual trigger")
                            })

                            # Split into sentences and queue TTS
                            sentences = split_into_sentences(speak_text)
                            logger.info(f"[{session_id}] Splitting into {len(sentences)} sentences")

                            # Set avatar to speaking state
                            if avatar_redis:
                                await avatar_redis.set_state(AvatarState.SPEAKING)

                            for i, sentence in enumerate(sentences):
                                tts_start = time.time()
                                audio_base64 = await text_to_speech(sentence, selected_voice, selected_tts_model)
                                logger.info(f"[{session_id}] TTS sentence {i+1}/{len(sentences)} in {time.time()-tts_start:.2f}s")

                                await websocket.send_json({
                                    "type": "cohost_audio_queued",
                                    "text": sentence,
                                    "audio_base64": audio_base64
                                })

                            pending_response = None
                        else:
                            logger.info(f"[{session_id}] Manual trigger - no pending response")

                    elif msg_type == "stop_speaking":
                        # Stop speaking immediately (P hotkey)
                        logger.info(f"[{session_id}] Stop speaking requested")
                        is_speaking = False
                        pending_response = None
                        audio_buffer.clear_all()
                        if avatar_redis:
                            await avatar_redis.set_state(AvatarState.IDLE)
                        await websocket.send_json({"type": "stop_speaking_ack"})

                    elif msg_type == "complete_section":
                        # Mark section as complete (E hotkey)
                        section_num = msg.get("section", 0)
                        if section_num > 0:
                            all_sections_covered.add(section_num)
                            state = await get_session_state(session_id) or {}
                            state["all_sections_covered"] = list(all_sections_covered)
                            await store_session_state(session_id, state)
                            logger.info(f"[{session_id}] Section {section_num} marked complete")
                            await websocket.send_json({
                                "type": "sections_progress",
                                "sections_covered": list(all_sections_covered)
                            })

                    elif msg_type == "go_to_section":
                        # Go to specific section (Q hotkey - go back)
                        section_num = msg.get("section", 0)
                        if section_num > 0:
                            # Remove this and all later sections from covered
                            all_sections_covered = {s for s in all_sections_covered if s < section_num}
                            state = await get_session_state(session_id) or {}
                            state["all_sections_covered"] = list(all_sections_covered)
                            await store_session_state(session_id, state)
                            logger.info(f"[{session_id}] Navigated to section {section_num}")
                            await websocket.send_json({
                                "type": "sections_progress",
                                "sections_covered": list(all_sections_covered)
                            })

                    elif msg_type == "recap_section":
                        # Recap current section (W hotkey)
                        section_num = msg.get("section", 1)
                        from core.redis_client import get_script_structure
                        structure = await get_script_structure(session_id)
                        if structure and structure.get("sections"):
                            sections = structure["sections"]
                            if 0 < section_num <= len(sections):
                                section = sections[section_num - 1]
                                section_title = section.get("title", f"Section {section_num}")
                                key_points = section.get("key_points", [])

                                # Build recap text
                                points_text = ""
                                for p in key_points[:3]:
                                    if isinstance(p, dict):
                                        points_text += f"- {p.get('text', '')}\n"
                                    else:
                                        points_text += f"- {p}\n"

                                recap_text = f"Current section: {section_title}\n{points_text}"
                                logger.info(f"[{session_id}] Recap section {section_num}: {section_title}")

                                await websocket.send_json({
                                    "type": "show_prompt",
                                    "text": recap_text
                                })

                    elif msg_type == "transcribe_now":
                        # Frontend VAD detected 2s pause - transcribe and process
                        if not script_loaded or is_speaking:
                            continue

                        if audio_buffer.total_bytes < MIN_AUDIO_BYTES:
                            logger.debug(f"[{session_id}] transcribe_now: not enough audio ({audio_buffer.total_bytes} bytes)")
                            continue

                        logger.info(f"[{session_id}] VAD transcribe_now ({audio_buffer.total_bytes} bytes)...")
                        start = time.time()

                        filepath = await audio_buffer.save_to_temp_file()
                        if filepath:
                            transcript = await transcribe_audio(filepath, whisper_context)
                            stt_time = time.time() - start
                            now = time.time()

                            # Skip hallucinations (just punctuation or very short)
                            clean_transcript = transcript.strip() if transcript else ""
                            is_hallucination = len(clean_transcript) < 3 or clean_transcript.replace(".", "").replace(",", "").strip() == ""

                            # Only accumulate and display non-hallucination transcripts
                            if transcript and not is_hallucination:
                                full_transcript += " " + transcript
                                full_transcript = full_transcript.strip()

                                # Set avatar to listening state when user speaks
                                if avatar_redis:
                                    await avatar_redis.set_state(AvatarState.LISTENING)

                                # Add to timeline
                                if session_start_time:
                                    elapsed_secs = now - session_start_time
                                    conversation_timeline.append({
                                        "time": format_timestamp(elapsed_secs),
                                        "speaker": "User",
                                        "text": transcript
                                    })
                                    if len(conversation_timeline) > 10:
                                        conversation_timeline.pop(0)

                                logger.info(f"[{session_id}] VAD STT in {stt_time:.2f}s: '{transcript[:60]}...'")

                                # Send transcript to frontend
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": transcript
                                })

                                # Accumulate transcript between brain calls
                                accumulated_transcript += " " + transcript
                                accumulated_transcript = accumulated_transcript.strip()

                            # Check brain trigger (even if this transcript was hallucination - periodic may have accumulated words)
                            accumulated_word_count = len(accumulated_transcript.split()) if accumulated_transcript else 0

                            # Check brain cooldown
                            time_since_brain = now - last_brain_call_time
                            if time_since_brain < BRAIN_CALL_COOLDOWN:
                                logger.info(f"[{session_id}] Brain skipped (cooldown: {time_since_brain:.1f}s < {BRAIN_CALL_COOLDOWN}s)")
                                continue

                            # Pause-based trigger: enough words to filter noise
                            if accumulated_word_count < MIN_WORDS_FOR_BRAIN:
                                logger.info(f"[{session_id}] Skipping brain: only {accumulated_word_count} words (min: {MIN_WORDS_FOR_BRAIN})")
                                continue

                            # Ready to call brain (pause detected + enough words)
                            # Check if brain is already processing
                            if brain_processing:
                                logger.info(f"[{session_id}] Brain skipped (already processing)")
                                continue

                            transcript_to_analyze = accumulated_transcript
                            accumulated_transcript = ""  # Reset accumulator
                            last_brain_call_time = now

                            # === Spawn Brain processing as background task ===
                            # Audio capture continues in main loop while Brain runs
                            async def process_brain_background():
                                nonlocal brain_processing, is_speaking, pending_response, last_prompt, last_remind_time, all_sections_covered

                                brain_processing = True
                                brain_start = time.time()

                                try:
                                    elapsed_mins = 0
                                    if session_start_time:
                                        elapsed_mins = (time.time() - session_start_time) / 60

                                    supports_emotions = selected_tts_model == "eleven_multilingual_v2"

                                    logger.info(f"[{session_id}] Brain started (background, {accumulated_word_count} words)")

                                    result = await analyze_progress(
                                        session_id,
                                        transcript_to_analyze,
                                        selected_style,
                                        selected_personality,
                                        supports_emotions,
                                        elapsed_mins=elapsed_mins,
                                        target_mins=target_duration_mins,
                                        sections_done=list(all_sections_covered),
                                        timeline=conversation_timeline,
                                        proactive=proactive_mode
                                    )
                                    brain_time = time.time() - brain_start

                                    action = result.get("action", "wait")
                                    sections_covered = result.get("sections_covered", [])

                                    # Track sections
                                    for sec in sections_covered:
                                        all_sections_covered.add(sec)

                                    state = await get_session_state(session_id) or {}
                                    state["all_sections_covered"] = list(all_sections_covered)
                                    await store_session_state(session_id, state)

                                    logger.info(f"[{session_id}] Brain completed in {brain_time:.2f}s: action={action}")

                                    # Send sections progress
                                    await websocket.send_json({
                                        "type": "sections_progress",
                                        "sections_covered": list(all_sections_covered),
                                        "elapsed_mins": round(elapsed_mins, 1),
                                        "target_mins": target_duration_mins,
                                        "pacing_hint": result.get("pacing_hint", "")
                                    })

                                    # Handle respond/enrich with queued TTS
                                    if action in ("respond", "enrich"):
                                        speak_text = result.get("speak_text", "")
                                        if speak_text:
                                            logger.info(f"[{session_id}] Brain {action}: '{speak_text[:60]}...'")

                                            if auto_response_enabled:
                                                # Auto mode: speak immediately
                                                is_speaking = True

                                                # Set avatar to speaking state and publish commands via Redis
                                                if avatar_redis and avatar_action_parser:
                                                    await avatar_redis.set_state(AvatarState.SPEAKING)
                                                    # Parse action tags from LLM response
                                                    parsed = avatar_action_parser.parse(speak_text)
                                                    # Publish commands for each parsed action
                                                    for action_item in parsed.get("actions", []):
                                                        action_type = action_item["type"]
                                                        action_name = action_item["name"]
                                                        action_params = action_item.get("params", {})
                                                        intensity = action_params.get("intensity", 1.0)

                                                        if action_type == "mood":
                                                            await avatar_redis.set_mood(action_name, intensity)
                                                        elif action_type == "gesture":
                                                            await avatar_redis.queue_gesture(action_name, source="llm", intensity=intensity)
                                                        elif action_type == "action":
                                                            await avatar_redis.send_action(action_name, action_params)
                                                        elif action_type in ("eye", "head", "body", "brow"):
                                                            # These are gesture aliases - send as gestures
                                                            await avatar_redis.queue_gesture(action_name, source="llm", intensity=intensity)

                                                    # Use clean text (tags stripped) for TTS
                                                    speak_text = parsed.get("clean_text", speak_text)

                                                # Add to timeline
                                                brain_now = time.time()
                                                elapsed_secs = brain_now - session_start_time if session_start_time else 0
                                                conversation_timeline.append({
                                                    "time": format_timestamp(elapsed_secs),
                                                    "speaker": "Buddy",
                                                    "text": speak_text
                                                })
                                                if len(conversation_timeline) > 10:
                                                    conversation_timeline.pop(0)

                                                # Clear audio buffer when speaking starts
                                                audio_buffer.clear_all()

                                                # Send speaking notification
                                                await websocket.send_json({
                                                    "type": "cohost_speaking",
                                                    "text": speak_text,
                                                    "reason": result.get("reason", "")
                                                })

                                                # Split into sentences and queue TTS
                                                sentences = split_into_sentences(speak_text)
                                                logger.info(f"[{session_id}] Splitting into {len(sentences)} sentences")

                                                # Set avatar to speaking state
                                                if avatar_redis:
                                                    await avatar_redis.set_state(AvatarState.SPEAKING)

                                                for i, sentence in enumerate(sentences):
                                                    tts_start = time.time()
                                                    audio_base64 = await text_to_speech(sentence, selected_voice, selected_tts_model)
                                                    logger.info(f"[{session_id}] TTS sentence {i+1}/{len(sentences)} in {time.time()-tts_start:.2f}s")

                                                    # Send queued audio chunk
                                                    await websocket.send_json({
                                                        "type": "cohost_audio_queued",
                                                        "text": sentence,
                                                        "audio_base64": audio_base64
                                                    })

                                            else:
                                                # Manual mode: store response, wait for hotkey
                                                pending_response = {
                                                    "speak_text": speak_text,
                                                    "result": result
                                                }
                                                logger.info(f"[{session_id}] Manual mode - response pending (press hotkey)")

                                                # Notify frontend that response is ready
                                                await websocket.send_json({
                                                    "type": "response_pending",
                                                    "text": speak_text,
                                                    "reason": result.get("reason", "")
                                                })

                                    elif action == "remind":
                                        prompt_text = result.get("prompt_text", "")
                                        if prompt_text and prompt_text != last_prompt:
                                            last_prompt = prompt_text
                                            last_remind_time = time.time()
                                            await websocket.send_json({
                                                "type": "show_prompt",
                                                "text": prompt_text
                                            })

                                except Exception as e:
                                    logger.error(f"[{session_id}] Brain background error: {e}", exc_info=True)
                                finally:
                                    brain_processing = False

                            # Launch Brain as background task - main loop continues receiving audio
                            brain_task = asyncio.create_task(process_brain_background())

            except asyncio.TimeoutError:
                # Timeout - periodic check now handled in audio chunk handler
                pass

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Client disconnected")
    except RuntimeError as e:
        if "disconnect" in str(e).lower():
            logger.info(f"[{session_id}] Client disconnected (runtime)")
        else:
            logger.error(f"[{session_id}] Runtime error: {e}")
    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}", exc_info=True)
    finally:
        audio_buffer.clear_all()
        # Cancel any running brain task
        if brain_task and not brain_task.done():
            brain_task.cancel()
            try:
                await brain_task
            except asyncio.CancelledError:
                pass
        await clear_session(session_id)
        # Cleanup VTuber Redis backbone
        if avatar_redis:
            try:
                # Stop idle processor before cleanup
                await avatar_redis.stop_idle_processor()
                await avatar_redis.cleanup()
                await avatar_redis.disconnect()
                logger.info(f"[{session_id}] VTuber Redis backbone disconnected")
            except Exception as e:
                logger.warning(f"[{session_id}] VTuber Redis cleanup error: {e}")
        logger.info(f"[{session_id}] Session cleaned up")
