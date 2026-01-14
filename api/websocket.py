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
MIN_WORDS_FOR_BRAIN = 20  # Minimum words before asking brain

# Cooldowns by style (set dynamically)
COOLDOWNS = {
    "aggressive": {"enrich": 20000, "remind": 15000},  # 20s enrich, 15s remind
    "balanced": {"enrich": 45000, "remind": 30000},    # 45s enrich, 30s remind
    "passive": {"enrich": 120000, "remind": 60000}     # 2min enrich (rare), 1min remind
}
ENRICH_COOLDOWN_MS = 45000  # Default, overridden by style
REMIND_COOLDOWN_MS = 30000  # Default, overridden by style


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """Main WebSocket endpoint - continuous listening loop."""
    await websocket.accept()

    from main import load_config
    config = load_config()

    session_id = str(uuid.uuid4())[:8]
    logger.info(f"[{session_id}] WebSocket connected")

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
    selected_style = "balanced"  # Co-host style: aggressive/balanced/passive
    selected_personality = "neutral"  # Co-host personality: positive/neutral/critical
    selected_tts_model = "eleven_flash_v2_5"  # TTS model: flash/turbo/multilingual
    session_start_time = None  # Track when presentation started
    target_duration_mins = 10  # Default target duration in minutes
    all_sections_covered = set()  # Track all sections covered so far
    conversation_timeline = []  # Track timestamped conversation: [{"time": "00:30", "speaker": "User", "text": "..."}]

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
                        if script_text:
                            logger.info(f"[{session_id}] Loading script, voice: {selected_voice}, style: {selected_style}, personality: {selected_personality}, tts: {selected_tts_model}")
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

                        # Get structure for welcome message
                        from core.redis_client import get_script_structure
                        structure = await get_script_structure(session_id)
                        total_sections = structure.get("total_sections", 1) if structure else 1
                        title = structure.get("title", "your presentation") if structure else "your presentation"

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

                    elif msg_type == "ready_for_audio":
                        is_speaking = False
                        # Clear any audio captured during TTS playback (echo)
                        audio_buffer.clear_all()
                        logger.info(f"[{session_id}] Ready for audio (TTS finished, buffer cleared)")

                    elif msg_type == "reset":
                        logger.info(f"[{session_id}] Resetting session")
                        await clear_session(session_id)
                        script_loaded = False
                        full_transcript = ""
                        audio_buffer.clear_all()
                        last_prompt = ""
                        last_remind_time = 0
                        last_enrich_time = 0
                        await websocket.send_json({"type": "reset_complete"})

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

                            if transcript:
                                full_transcript += " " + transcript
                                full_transcript = full_transcript.strip()
                                word_count = len(full_transcript.split())

                                # Add to timeline
                                now = time.time()
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

                                # Ask brain if we have enough content
                                if word_count >= MIN_WORDS_FOR_BRAIN:
                                    brain_start = time.time()
                                    elapsed_mins = 0
                                    if session_start_time:
                                        elapsed_mins = (now - session_start_time) / 60

                                    supports_emotions = selected_tts_model == "eleven_multilingual_v2"

                                    result = await analyze_progress(
                                        session_id,
                                        transcript,
                                        selected_style,
                                        selected_personality,
                                        supports_emotions,
                                        elapsed_mins=elapsed_mins,
                                        target_mins=target_duration_mins,
                                        sections_done=list(all_sections_covered),
                                        timeline=conversation_timeline
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

                                    logger.info(f"[{session_id}] VAD Brain in {brain_time:.2f}s: action={action}")

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
                                            is_speaking = True

                                            # Add to timeline
                                            elapsed_secs = now - session_start_time if session_start_time else 0
                                            conversation_timeline.append({
                                                "time": format_timestamp(elapsed_secs),
                                                "speaker": "Buddy",
                                                "text": speak_text
                                            })
                                            if len(conversation_timeline) > 10:
                                                conversation_timeline.pop(0)

                                            logger.info(f"[{session_id}] VAD {action}: '{speak_text[:60]}...'")

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

                                    elif action == "remind":
                                        prompt_text = result.get("prompt_text", "")
                                        if prompt_text and prompt_text != last_prompt:
                                            last_prompt = prompt_text
                                            last_remind_time = now
                                            await websocket.send_json({
                                                "type": "show_prompt",
                                                "text": prompt_text
                                            })

                        audio_buffer.clear_accumulator()

            except asyncio.TimeoutError:
                # Timeout - check if we should transcribe
                pass

            # All transcription is now triggered by VAD (transcribe_now message)
            # No periodic transcription - wait for user to pause

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
        await clear_session(session_id)
        logger.info(f"[{session_id}] Session cleaned up")
