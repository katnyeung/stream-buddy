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
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.audio_buffer import AudioBuffer
from core.stt_client import transcribe_audio
from core.tts_client import text_to_speech
from core.script_manager import parse_script, analyze_progress, get_current_prompt
from core.redis_client import clear_session

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# Timing configs
TRANSCRIBE_INTERVAL_MS = 15000  # Transcribe every 15 seconds
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
    last_transcribe_time = time.time()
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
                        last_transcribe_time = time.time()
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

            except asyncio.TimeoutError:
                # Timeout - check if we should transcribe
                pass

            # Skip processing if speaking or no script
            if is_speaking or not script_loaded:
                continue

            # Check if we have enough audio and time has passed
            now = time.time()
            time_since_last = (now - last_transcribe_time) * 1000

            if audio_buffer.total_bytes >= MIN_AUDIO_BYTES and time_since_last >= TRANSCRIBE_INTERVAL_MS:
                # Save and transcribe
                logger.info(f"[{session_id}] Transcribing ({audio_buffer.total_bytes} bytes)...")
                start = time.time()

                filepath = await audio_buffer.save_to_temp_file()
                if filepath:
                    transcript = await transcribe_audio(filepath, whisper_context)
                    stt_time = time.time() - start

                    if transcript:
                        full_transcript += " " + transcript
                        full_transcript = full_transcript.strip()
                        word_count = len(full_transcript.split())

                        # Add to timeline with timestamp
                        if session_start_time:
                            elapsed_secs = now - session_start_time
                            conversation_timeline.append({
                                "time": format_timestamp(elapsed_secs),
                                "speaker": "User",
                                "text": transcript
                            })
                            # Keep last 10 entries
                            if len(conversation_timeline) > 10:
                                conversation_timeline.pop(0)

                        logger.info(f"[{session_id}] STT in {stt_time:.2f}s: '{transcript[:60]}...'")

                        # Send transcript to frontend
                        await websocket.send_json({
                            "type": "transcript",
                            "text": transcript
                        })

                        # Only ask brain when we have enough content
                        if word_count >= MIN_WORDS_FOR_BRAIN:
                            brain_start = time.time()
                            # Calculate elapsed time
                            elapsed_mins = 0
                            if session_start_time:
                                elapsed_mins = (now - session_start_time) / 60

                            # Check if premium model supports emotions
                            supports_emotions = selected_tts_model == "eleven_multilingual_v2"

                            # Pass timing, coverage, and conversation timeline to brain
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
                            time_since_remind = (now - last_remind_time) * 1000
                            time_since_enrich = (now - last_enrich_time) * 1000
                            sections_covered = result.get("sections_covered", [])

                            # Track all sections covered
                            for sec in sections_covered:
                                all_sections_covered.add(sec)

                            logger.info(f"[{session_id}] Brain in {brain_time:.2f}s: action={action}, sections: {sections_covered}")
                            logger.info(f"[{session_id}] Elapsed: {elapsed_mins:.1f}/{target_duration_mins}min, covered: {list(all_sections_covered)}")

                            # Send sections progress to frontend
                            await websocket.send_json({
                                "type": "sections_progress",
                                "sections_covered": list(all_sections_covered),
                                "elapsed_mins": round(elapsed_mins, 1),
                                "target_mins": target_duration_mins,
                                "pacing_hint": result.get("pacing_hint", "")
                            })

                            # Get style-specific cooldowns
                            style_cooldowns = COOLDOWNS.get(selected_style, COOLDOWNS["balanced"])
                            enrich_cooldown = style_cooldowns["enrich"]
                            remind_cooldown = style_cooldowns["remind"]

                            if action == "remind":
                                # Visual prompt only - suggest next topic
                                prompt_text = result.get("prompt_text", "")
                                if prompt_text and prompt_text != last_prompt and time_since_remind >= remind_cooldown:
                                    last_prompt = prompt_text
                                    last_remind_time = now
                                    logger.info(f"[{session_id}] Remind: '{prompt_text}'")
                                    await websocket.send_json({
                                        "type": "show_prompt",
                                        "text": prompt_text
                                    })

                            elif action == "enrich":
                                # Co-host adds value with interesting info
                                speak_text = result.get("speak_text", "")
                                if speak_text and time_since_enrich >= enrich_cooldown:
                                    is_speaking = True
                                    last_enrich_time = now

                                    # Add to timeline
                                    elapsed_secs = now - session_start_time if session_start_time else 0
                                    conversation_timeline.append({
                                        "time": format_timestamp(elapsed_secs),
                                        "speaker": "Buddy",
                                        "text": speak_text
                                    })
                                    if len(conversation_timeline) > 10:
                                        conversation_timeline.pop(0)

                                    logger.info(f"[{session_id}] Enrich: '{speak_text[:60]}...'")

                                    audio_buffer.clear_all()

                                    await websocket.send_json({
                                        "type": "cohost_speaking",
                                        "text": speak_text,
                                        "reason": result.get("reason", "")
                                    })

                                    tts_start = time.time()
                                    audio_base64 = await text_to_speech(speak_text, selected_voice, selected_tts_model)
                                    logger.info(f"[{session_id}] TTS in {time.time()-tts_start:.2f}s")

                                    await websocket.send_json({
                                        "type": "cohost_audio",
                                        "text": speak_text,
                                        "audio_base64": audio_base64
                                    })

                            elif action == "respond":
                                # Direct response to speaker - no cooldown
                                speak_text = result.get("speak_text", "")
                                if speak_text:
                                    is_speaking = True
                                    last_enrich_time = now  # Reset enrich cooldown too

                                    # Add to timeline
                                    elapsed_secs = now - session_start_time if session_start_time else 0
                                    conversation_timeline.append({
                                        "time": format_timestamp(elapsed_secs),
                                        "speaker": "Buddy",
                                        "text": speak_text
                                    })
                                    if len(conversation_timeline) > 10:
                                        conversation_timeline.pop(0)

                                    logger.info(f"[{session_id}] Respond: '{speak_text[:60]}...'")

                                    audio_buffer.clear_all()

                                    await websocket.send_json({
                                        "type": "cohost_speaking",
                                        "text": speak_text,
                                        "reason": result.get("reason", "")
                                    })

                                    tts_start = time.time()
                                    audio_base64 = await text_to_speech(speak_text, selected_voice, selected_tts_model)
                                    logger.info(f"[{session_id}] TTS in {time.time()-tts_start:.2f}s")

                                    await websocket.send_json({
                                        "type": "cohost_audio",
                                        "text": speak_text,
                                        "audio_base64": audio_base64
                                    })

                    audio_buffer.clear_accumulator()
                    last_transcribe_time = now

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
