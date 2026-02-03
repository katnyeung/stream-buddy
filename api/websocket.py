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
from core.stt_client import transcribe_audio, apply_stt_corrections
from core.tts_client import text_to_speech, text_to_speech_stream, use_streaming
from core.script_manager import parse_script, analyze_progress, get_current_prompt, match_section_keywords
from core.redis_client import clear_session, store_session_state, get_session_state, get_script_structure, store_prediction_status

# Prediction cache for pre-generated TTS (optional feature)
try:
    from core.prediction_cache import PredictionCache
    PREDICTION_CACHE_AVAILABLE = True
except ImportError:
    PREDICTION_CACHE_AVAILABLE = False
    PredictionCache = None

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


async def check_keyword_completion(
    session_id: str,
    transcript: str,
    all_sections_covered: set,
    threshold: float = 0.5
) -> tuple[set, list, dict]:
    """
    Check if transcript matches section keywords and mark sections as complete.

    Runs BEFORE the brain call to update section progress locally.

    Args:
        session_id: Session identifier
        transcript: Accumulated transcript to check
        all_sections_covered: Current set of completed sections
        threshold: Match ratio required (default 0.5 = 50%)

    Returns:
        (updated_sections_covered, newly_completed, match_progress): Updated set, list of newly completed, and match progress dict
    """
    structure = await get_script_structure(session_id)
    if not structure:
        return all_sections_covered, [], {}

    sections = structure.get("sections", [])
    newly_completed = []
    match_progress = {}  # {section_id: {ratio, matched, unmatched, keywords}}

    for section in sections:
        section_id = section.get("id", 0)
        section_title = section.get("title", f"Section {section_id}")

        # Get section keywords (handle string or array)
        section_keywords = section.get("section_keywords", [])
        if isinstance(section_keywords, str):
            # LLM returned string instead of array - split it
            section_keywords = [k.strip() for k in re.split(r'[,\s]+', section_keywords) if k.strip()]

        # Handle case where LLM concatenated keywords into one string like "helloEveryoneToday"
        # Split on camelCase boundaries and common patterns
        expanded_keywords = []
        for kw in section_keywords:
            if len(kw) > 15:  # Likely concatenated - try to split
                # Split on camelCase: "helloEveryone" -> ["hello", "Everyone"]
                parts = re.split(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', kw)
                # Also split on apostrophe: "I'mtoday" -> ["I'm", "today"] (rough)
                final_parts = []
                for p in parts:
                    if "'" in p and len(p) > 4:
                        # Split around apostrophe keeping the apostrophe word
                        apos_parts = re.split(r"(?<=')(?=[a-z])", p)
                        final_parts.extend(apos_parts)
                    else:
                        final_parts.append(p)
                expanded_keywords.extend([p.lower() for p in final_parts if len(p) >= 2])
            else:
                expanded_keywords.append(kw.lower())
        section_keywords = expanded_keywords if expanded_keywords else section_keywords
        if not section_keywords:
            # Fallback: extract words from speech-type key_points
            for point in section.get("key_points", []):
                if isinstance(point, dict) and point.get("type") != "action":
                    text = point.get("text", "")
                    # Extract significant words (4+ chars)
                    words = [w.lower() for w in text.split() if len(w) >= 4]
                    section_keywords.extend(words[:3])

        if not section_keywords:
            continue

        # Check keyword match (returns 3-tuple now)
        is_complete, match_ratio, match_details = match_section_keywords(transcript, section_keywords, threshold)

        # Store progress for all sections (even already completed)
        match_progress[section_id] = {
            "title": section_title,
            "ratio": round(match_ratio * 100),  # percentage
            "matched": match_details["matched"],
            "unmatched": match_details["unmatched"],
            "keywords": section_keywords,
            "complete": section_id in all_sections_covered or is_complete
        }

        # Skip already completed sections for completion tracking
        if section_id in all_sections_covered:
            continue

        if is_complete:
            all_sections_covered.add(section_id)
            newly_completed.append(section_id)
            logging.info(f"[{session_id}] Section {section_id} COMPLETE ({match_ratio:.0%}): matched={match_details['matched']}")
        else:
            # Log progress for debugging
            if match_details["matched"]:
                logging.info(f"[{session_id}] Section {section_id} progress ({match_ratio:.0%}): matched={match_details['matched']}, need={match_details['unmatched']}")

    return all_sections_covered, newly_completed, match_progress


async def process_tts_background(
    sentences: list[str],
    voice: str,
    model: str,
    websocket,
    session_id: str,
    avatar_redis=None,
):
    """Process TTS for sentences in background, sending audio as each completes.

    This runs as a background task so the main websocket loop isn't blocked.
    """
    try:
        if avatar_redis:
            await avatar_redis.set_state(AvatarState.SPEAKING)

        for i, sentence in enumerate(sentences):
            tts_start = time.time()
            try:
                if use_streaming():
                    chunk_idx = 0
                    async for audio_base64 in text_to_speech_stream(sentence, voice, model):
                        chunk_idx += 1
                        await websocket.send_json({
                            "type": "cohost_audio_queued",
                            "text": sentence if chunk_idx == 1 else "",
                            "audio_base64": audio_base64,
                            "is_stream_chunk": True,
                            "chunk_index": chunk_idx
                        })
                    logging.info(f"[{session_id}] BG TTS {i+1}/{len(sentences)} streamed in {time.time()-tts_start:.2f}s")
                else:
                    audio_base64 = await text_to_speech(sentence, voice, model)
                    logging.info(f"[{session_id}] BG TTS {i+1}/{len(sentences)} in {time.time()-tts_start:.2f}s")
                    await websocket.send_json({
                        "type": "cohost_audio_queued",
                        "text": sentence,
                        "audio_base64": audio_base64
                    })
            except Exception as e:
                logging.error(f"[{session_id}] BG TTS error for sentence {i+1}: {e}")

        logging.info(f"[{session_id}] BG TTS complete: {len(sentences)} sentences")
    except Exception as e:
        logging.error(f"[{session_id}] BG TTS task error: {e}")


async def process_tts_buffered(
    sentences: list[str],
    voice: str,
    model: str,
    websocket,
    session_id: str,
    pending_audio_chunks: list,
    speak_text: str,
    result: dict,
):
    """Process TTS for sentences and buffer audio, notifying when first chunk is ready.

    This is used in manual mode - audio is buffered until user presses T.
    """
    try:
        first_chunk_sent = False

        for i, sentence in enumerate(sentences):
            tts_start = time.time()
            try:
                if use_streaming():
                    chunk_idx = 0
                    async for audio_base64 in text_to_speech_stream(sentence, voice, model):
                        chunk_idx += 1
                        # Buffer the audio chunk
                        pending_audio_chunks.append({
                            "text": sentence if chunk_idx == 1 else "",
                            "audio_base64": audio_base64,
                            "is_stream_chunk": True,
                            "chunk_index": chunk_idx
                        })
                        # Notify frontend when first chunk is ready
                        if not first_chunk_sent:
                            first_chunk_sent = True
                            await websocket.send_json({
                                "type": "audio_ready",
                                "text": speak_text,
                                "reason": result.get("reason", "")
                            })
                            logging.info(f"[{session_id}] Manual mode: first audio chunk ready, waiting for T")
                    logging.info(f"[{session_id}] Buffered TTS {i+1}/{len(sentences)} streamed in {time.time()-tts_start:.2f}s")
                else:
                    audio_base64 = await text_to_speech(sentence, voice, model)
                    logging.info(f"[{session_id}] Buffered TTS {i+1}/{len(sentences)} in {time.time()-tts_start:.2f}s")
                    # Buffer the audio chunk
                    pending_audio_chunks.append({
                        "text": sentence,
                        "audio_base64": audio_base64
                    })
                    # Notify frontend when first chunk is ready
                    if not first_chunk_sent:
                        first_chunk_sent = True
                        await websocket.send_json({
                            "type": "audio_ready",
                            "text": speak_text,
                            "reason": result.get("reason", "")
                        })
                        logging.info(f"[{session_id}] Manual mode: first audio chunk ready, waiting for T")
            except Exception as e:
                logging.error(f"[{session_id}] Buffered TTS error for sentence {i+1}: {e}")

        logging.info(f"[{session_id}] Buffered TTS complete: {len(sentences)} sentences, {len(pending_audio_chunks)} chunks ready")
    except Exception as e:
        logging.error(f"[{session_id}] Buffered TTS task error: {e}")


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
    pending_audio_chunks = []  # Buffered audio chunks for manual mode
    pending_audio_ready = False  # True when first audio chunk is ready

    # Concurrent Brain processing
    brain_task = None  # Background task for Brain processing
    brain_processing = False  # Flag to prevent concurrent brain calls

    # Prediction cache (optional feature - pre-generated TTS for keywords)
    prediction_cache = None
    use_prediction_cache = False

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
                                    # Accumulate to BOTH transcripts (fix: was missing full_transcript)
                                    full_transcript += " " + transcript
                                    full_transcript = full_transcript.strip()
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
                        use_prediction_cache = msg.get("use_prediction_cache", False)  # Prediction cache feature flag
                        if script_text:
                            logger.info(f"[{session_id}] Loading script, voice: {selected_voice}, style: {selected_style}, personality: {selected_personality}, tts: {selected_tts_model}, proactive: {proactive_mode}, prediction_cache: {use_prediction_cache}")
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

                            # === PROACTIVE MODE: Preload welcome speech for instant playback on Start ===
                            if proactive_mode:
                                async def preload_welcome_bg():
                                    try:
                                        from core.redis_client import get_redis
                                        from core.tts_client import text_to_speech
                                        import re

                                        total_sections = structure.get("total_sections", len(structure.get("sections", [])))
                                        title = structure.get("title", "your presentation")

                                        first_section_title = ""
                                        sections = structure.get("sections", [])
                                        if sections:
                                            first_section_title = sections[0].get("title", "the first topic")

                                        welcome_text = f"[mood:excited] [gesture:wave] Hey everyone! I'm Buddy, your host today. [head:nod] We're covering {title} with {total_sections} topics, starting with {first_section_title}. [gesture:present] So, what should we know about this?"

                                        # Strip tags for TTS
                                        clean_welcome = re.sub(r'\[[\w:,]+\]', '', welcome_text).strip()

                                        logger.info(f"[{session_id}] PROACTIVE: Preloading welcome speech TTS...")
                                        audio_base64 = await text_to_speech(clean_welcome, selected_voice, selected_tts_model)

                                        if audio_base64:
                                            r = await get_redis()
                                            cache_key = f"stream:{session_id}:welcome_speech"
                                            await r.hset(cache_key, mapping={
                                                "text": welcome_text,
                                                "audio_base64": audio_base64
                                            })
                                            await r.expire(cache_key, 3600)
                                            logger.info(f"[{session_id}] PROACTIVE: Welcome speech cached (ready for Start)")

                                    except Exception as e:
                                        logger.error(f"[{session_id}] Failed to preload welcome: {e}")

                                asyncio.create_task(preload_welcome_bg())

                            # Initialize prediction cache if feature enabled
                            if use_prediction_cache and PREDICTION_CACHE_AVAILABLE:
                                # Clear any old prediction cache first
                                from core.redis_client import get_redis
                                r = await get_redis()
                                old_keys = await r.keys(f"stream:{session_id}:voice_cache:*")
                                if old_keys:
                                    await r.delete(*old_keys)
                                    logger.info(f"[{session_id}] Cleared {len(old_keys)} old prediction cache entries")

                                prediction_cache = PredictionCache(session_id)
                                logger.info(f"[{session_id}] Starting prediction cache generation in background...")

                                # Notify frontend that prediction generation is starting
                                await websocket.send_json({
                                    "type": "prediction_status",
                                    "status": "generating",
                                    "message": "Generating prediction cache..."
                                })

                                # Generate predictions in background (don't block UI)
                                async def generate_predictions_bg():
                                    try:
                                        result = await prediction_cache.generate_all_predictions(
                                            structure, selected_voice, selected_tts_model,
                                            proactive_mode=proactive_mode,
                                            target_duration_mins=target_duration_mins
                                        )
                                        # Store status in Redis for outline page (always save, even if WS closed)
                                        await store_prediction_status(session_id, {
                                            "status": "ready",
                                            "generated": result.get("generated", 0),
                                            "keywords": result.get("keywords", []),
                                            "predictions_by_section": prediction_cache.get_predictions_by_section()
                                        })
                                        # Notify frontend (only if websocket still open)
                                        try:
                                            await websocket.send_json({
                                                "type": "prediction_status",
                                                "status": "ready",
                                                "cached_count": result.get("generated", 0),
                                                "keywords": result.get("keywords", [])
                                            })
                                        except RuntimeError:
                                            # Websocket already closed - that's ok, data is in Redis
                                            logger.info(f"[{session_id}] Prediction cache ready (WS closed, saved to Redis)")
                                    except Exception as e:
                                        logger.error(f"[{session_id}] Prediction cache generation failed: {e}")
                                        try:
                                            await websocket.send_json({
                                                "type": "prediction_status",
                                                "status": "error",
                                                "message": str(e)
                                            })
                                        except RuntimeError:
                                            pass  # Websocket closed, ignore

                                asyncio.create_task(generate_predictions_bg())

                    elif msg_type == "start_presentation":
                        # User clicked start - begin timer
                        session_start_time = time.time()
                        all_sections_covered = set()

                        # Start avatar idle processor
                        if avatar_redis:
                            await avatar_redis.start_idle_processor()
                            logger.info(f"[{session_id}] Avatar idle processor started")

                        if proactive_mode:
                            # === PROACTIVE MODE: AI speaks first (reporter style) ===
                            is_speaking = True

                            # Try cached welcome first
                            cached_welcome = None
                            try:
                                from core.redis_client import get_redis
                                r = await get_redis()
                                cache_key = f"stream:{session_id}:welcome_speech"
                                data = await r.hgetall(cache_key)
                                if data and data.get("audio_base64"):
                                    cached_welcome = {
                                        "text": data.get("text", ""),
                                        "audio_base64": data["audio_base64"]
                                    }
                            except Exception as e:
                                logger.warning(f"[{session_id}] Failed to get cached welcome: {e}")

                            if cached_welcome:
                                # Instant playback from cache!
                                welcome_text = cached_welcome["text"]
                                logger.info(f"[{session_id}] PROACTIVE: Playing CACHED welcome (instant)")

                                await websocket.send_json({
                                    "type": "cohost_speaking",
                                    "text": welcome_text,
                                    "reason": "Reporter welcome (cached)",
                                    "from_cache": True
                                })
                                await websocket.send_json({
                                    "type": "cohost_audio_queued",
                                    "text": welcome_text,
                                    "audio_base64": cached_welcome["audio_base64"],
                                    "from_cache": True
                                })

                                if avatar_redis:
                                    await avatar_redis.set_state(AvatarState.SPEAKING)
                            else:
                                # Fallback: Generate welcome on-the-fly
                                structure = await get_script_structure(session_id)
                                total_sections = structure.get("total_sections", 1) if structure else 1
                                title = structure.get("title", "your presentation") if structure else "your presentation"

                                first_section_title = ""
                                if structure and structure.get("sections"):
                                    first_section = structure["sections"][0]
                                    first_section_title = first_section.get("title", "the first topic")

                                welcome_text = f"[mood:excited] [gesture:wave] Hey everyone! I'm Buddy, your host today. [head:nod] We're covering {title} with {total_sections} topics, starting with {first_section_title}. [gesture:present] So, what should we know about this?"

                                logger.info(f"[{session_id}] PROACTIVE: Generating welcome TTS (not cached)")

                                await websocket.send_json({
                                    "type": "cohost_speaking",
                                    "text": welcome_text,
                                    "reason": "Reporter welcome"
                                })

                                sentences = split_into_sentences(welcome_text)
                                asyncio.create_task(process_tts_background(
                                    sentences, selected_voice, selected_tts_model,
                                    websocket, session_id, avatar_redis
                                ))
                        else:
                            # === NORMAL MODE: User speaks first, AI responds ===
                            is_speaking = False
                            logger.info(f"[{session_id}] NORMAL: Started, listening for user speech")

                            await websocket.send_json({
                                "type": "presentation_started",
                                "message": "Listening... You speak first!"
                            })

                            if avatar_redis:
                                await avatar_redis.set_state(AvatarState.LISTENING)

                    elif msg_type == "ready_for_audio":
                        is_speaking = False
                        # Clear any audio captured during TTS playback (echo)
                        audio_buffer.clear_all()
                        # Clear accumulated transcript so fresh speech gets checked
                        accumulated_transcript = ""
                        logger.info(f"[{session_id}] Ready for audio (TTS finished, buffer+transcript cleared)")

                        # Set avatar to idle state
                        if avatar_redis:
                            await avatar_redis.set_state(AvatarState.IDLE)

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
                        # Manual hotkey pressed - release the buffered audio
                        if pending_response and pending_audio_chunks:
                            logger.info(f"[{session_id}] Manual trigger - releasing {len(pending_audio_chunks)} buffered audio chunks")
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

                            # Set avatar state to speaking if VTuber is enabled
                            if avatar_redis:
                                await avatar_redis.set_state(AvatarState.SPEAKING)

                            # Send all buffered audio chunks immediately
                            for chunk in pending_audio_chunks:
                                await websocket.send_json({
                                    "type": "cohost_audio_queued",
                                    **chunk
                                })

                            logger.info(f"[{session_id}] Manual trigger: sent {len(pending_audio_chunks)} audio chunks")

                            # Clear pending state
                            pending_response = None
                            pending_audio_chunks.clear()
                            pending_audio_ready = False
                        elif pending_response and not pending_audio_chunks:
                            logger.info(f"[{session_id}] Manual trigger - audio still processing, please wait")
                        else:
                            logger.info(f"[{session_id}] Manual trigger - no pending response")

                    elif msg_type == "trigger_cached_keyword":
                        # Keyboard hotkey triggered - play cached keyword response
                        keyword = data.get("keyword")
                        if keyword and prediction_cache:
                            cached = await prediction_cache.get_by_keyword(keyword)
                            if cached:
                                logger.info(f"[{session_id}] Hotkey trigger: '{keyword}' -> instant play")
                                is_speaking = True
                                audio_buffer.clear_all()

                                await websocket.send_json({
                                    "type": "cohost_speaking",
                                    "text": cached["response_text"],
                                    "reason": f"Hotkey: {keyword}",
                                    "from_cache": True
                                })
                                await websocket.send_json({
                                    "type": "cohost_audio_queued",
                                    "text": cached["response_text"],
                                    "audio_base64": cached["audio_base64"],
                                    "from_cache": True
                                })
                                await websocket.send_json({
                                    "type": "prediction_hit",
                                    "keyword": cached["keyword"],
                                    "section_id": cached.get("section_id", 0)
                                })
                                if avatar_redis:
                                    await avatar_redis.set_state(AvatarState.SPEAKING)
                            else:
                                logger.warning(f"[{session_id}] No cache for keyword: {keyword}")
                        else:
                            logger.warning(f"[{session_id}] Hotkey trigger without keyword or cache")

                    elif msg_type == "stop_speaking":
                        # Stop speaking immediately (P hotkey)
                        logger.info(f"[{session_id}] Stop speaking requested")
                        is_speaking = False
                        pending_response = None
                        pending_audio_chunks.clear()
                        pending_audio_ready = False
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

                            # Trigger dynamic prediction for next section
                            structure = await get_script_structure(session_id)
                            if prediction_cache and structure:
                                total_sections = structure.get("total_sections", len(structure.get("sections", [])))
                                if section_num < total_sections:
                                    logger.info(f"[{session_id}] Triggering dynamic predictions for section {section_num + 1}")
                                    asyncio.create_task(
                                        prediction_cache.generate_dynamic_predictions(
                                            next_section_id=section_num + 1,
                                            recent_transcript=accumulated_transcript[-500:] if accumulated_transcript else "",
                                            structure=structure,
                                            voice=selected_voice,
                                            tts_model=selected_tts_model,
                                            websocket=websocket
                                        )
                                    )

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

                            # === Check keyword completion BEFORE brain call ===
                            # This updates section progress locally without LLM
                            all_sections_covered, newly_completed, match_progress = await check_keyword_completion(
                                session_id,
                                full_transcript,  # Use full transcript for better matching
                                all_sections_covered,
                                threshold=0.5  # 50% of keywords needed
                            )

                            # Save keyword_progress to Redis for polling API
                            state = await get_session_state(session_id) or {}
                            state["keyword_progress"] = match_progress
                            state["all_sections_covered"] = list(all_sections_covered)
                            await store_session_state(session_id, state)

                            # Send match progress to frontend (shows keyword match status)
                            await websocket.send_json({
                                "type": "keyword_progress",
                                "sections_covered": list(all_sections_covered),
                                "keyword_completed": newly_completed,
                                "match_progress": match_progress  # {section_id: {ratio, matched, unmatched, keywords}}
                            })

                            if newly_completed:
                                logger.info(f"[{session_id}] Keyword completion: sections {newly_completed} marked complete")

                            # === Spawn Brain processing as background task ===
                            # Audio capture continues in main loop while Brain runs
                            # Set flag BEFORE launching task to prevent double-trigger
                            brain_processing = True

                            async def process_brain_background():
                                nonlocal brain_processing, is_speaking, pending_response, last_prompt, last_remind_time, all_sections_covered, accumulated_transcript

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
                                    # Note: sections_covered now handled by keyword matching before brain call

                                    # Save state (sections already updated by keyword matching)
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

                                                # Split into sentences and process TTS in background (non-blocking)
                                                sentences = split_into_sentences(speak_text)
                                                logger.info(f"[{session_id}] Brain response: queueing {len(sentences)} sentences for background TTS")
                                                asyncio.create_task(process_tts_background(
                                                    sentences, selected_voice, selected_tts_model,
                                                    websocket, session_id, avatar_redis
                                                ))

                                            else:
                                                # Manual mode: start TTS processing but buffer audio
                                                # Clear any previous pending audio
                                                pending_audio_chunks.clear()
                                                pending_audio_ready = False

                                                pending_response = {
                                                    "speak_text": speak_text,
                                                    "result": result
                                                }
                                                logger.info(f"[{session_id}] Manual mode - processing TTS in background")

                                                # Notify frontend that we're processing (text preview)
                                                await websocket.send_json({
                                                    "type": "response_pending",
                                                    "text": speak_text,
                                                    "reason": result.get("reason", "")
                                                })

                                                # Start TTS processing to buffer audio
                                                # When first chunk is ready, it will send 'audio_ready' message
                                                sentences = split_into_sentences(speak_text)
                                                asyncio.create_task(process_tts_buffered(
                                                    sentences, selected_voice, selected_tts_model,
                                                    websocket, session_id, pending_audio_chunks,
                                                    speak_text, result
                                                ))

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
