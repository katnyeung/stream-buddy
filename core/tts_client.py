"""
Text-to-Speech client using ElevenLabs.
"""
import os
import re
import io
import base64
from typing import AsyncIterator
import httpx
from elevenlabs import ElevenLabs

client: ElevenLabs | None = None
http_client: httpx.AsyncClient | None = None


def get_client() -> ElevenLabs:
    global client
    if client is None:
        base_url = os.getenv("ELEVENLABS_BASE_URL")
        api_key = os.getenv("ELEVENLABS_API_KEY", "not-needed-for-local")
        if base_url:
            # Use local Qwen3-TTS API
            client = ElevenLabs(api_key=api_key, base_url=base_url)
            print(f"[TTS] Using custom base URL: {base_url}")
        else:
            client = ElevenLabs(api_key=api_key)
    return client


def get_default_voice() -> str:
    """Get default voice ID from env."""
    return os.getenv("ELEVENLABS_VOICE_NARRATOR") or os.getenv("ELEVENLABS_VOICE_CIPHER") or "21m00Tcm4TlvDq8ikWAM"


def get_model() -> str:
    """Get model from env."""
    return os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")


def should_strip_tags() -> bool:
    """Check if audio tags should be stripped."""
    return os.getenv("ELEVENLABS_STRIP_TAGS", "true").lower() == "true"


# Premium models that support ElevenLabs audio tags
PREMIUM_MODELS = {
    "eleven_multilingual_v2",
    "eleven_v3",
    "eleven_turbo_v2_5",  # turbo also supports tags
}


def strip_action_tags(text: str) -> str:
    """Remove VTuber action tags - these are for avatar control, not TTS."""
    # Remove VTuber control tags like [mood:X], [gesture:Y], [head:Z,repeat:2,delay:500], etc.
    return re.sub(r'\[(?:mood|gesture|action|eye|head|body|brow):\w+(?:,[^\]]+)?\]', '', text).strip()


def strip_all_tags(text: str) -> str:
    """Remove ALL bracketed tags for models that don't support them."""
    return re.sub(r'\[.*?\]', '', text).strip()


def is_premium_model(model_id: str) -> bool:
    """Check if model supports ElevenLabs audio tags."""
    return model_id in PREMIUM_MODELS


async def text_to_speech(text: str, voice: str = None, model: str = None) -> str:
    """
    Convert text to speech using ElevenLabs.

    Args:
        text: Text to convert to speech
        voice: ElevenLabs voice ID (default: from env)
        model: ElevenLabs model ID (default: from env)

    Returns:
        Base64 encoded audio data (MP3)
    """
    if not text or not text.strip():
        return ""

    # Use provided voice or default from env
    voice_id = voice if voice else get_default_voice()
    model_id = model if model else get_model()

    # Log which model is being used
    print(f"[TTS] Using model: {model_id}")

    # Always strip VTuber action tags (mood, gesture, head, etc.) - avatar-only control
    clean_text = strip_action_tags(text)

    # For non-premium models, also strip ElevenLabs audio tags
    # Premium models keep tags like [HAPPY], [EXCITED], [GASP], [SIGH] etc.
    if not is_premium_model(model_id):
        clean_text = strip_all_tags(clean_text)
        print(f"[TTS] Non-premium model - stripped all tags")
    else:
        print(f"[TTS] Premium model - keeping ElevenLabs audio tags")

    if not clean_text:
        return ""

    client = get_client()

    try:
        # ElevenLabs SDK v2.x: convert() returns an iterator (works for both streaming and non-streaming)
        # The response is chunked, so it works with local wrappers that return StreamingResponse
        audio_generator = client.text_to_speech.convert(
            text=clean_text,
            voice_id=voice_id,
            model_id=model_id,
            output_format="mp3_44100_128"
        )

        # Collect audio bytes from generator
        audio_bytes = b''.join(audio_generator)

        # Encode to base64
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        return audio_base64

    except Exception as e:
        print(f"TTS error: {e}")
        return ""


def get_voice_id(voice_name: str) -> str:
    """Get ElevenLabs voice ID - returns as-is if already an ID, otherwise lookup."""
    # If it looks like a voice ID (alphanumeric), return as-is
    if voice_name and len(voice_name) > 15:
        return voice_name

    # Common voice name mapping
    VOICE_IDS = {
        "Rachel": "21m00Tcm4TlvDq8ikWAM",
        "Domi": "AZnzlk1XvdvUeBnXmlld",
        "Bella": "EXAVITQu4vr4xnSDxMaL",
        "Antoni": "ErXwobaYiN019PkySvjV",
        "Elli": "MF3mGyEYCl7XYWbV9V6O",
        "Josh": "TxGEqnHWrfWFTfGW9XjX",
        "Arnold": "VR6AewLTigWG4xSOukaG",
        "Adam": "pNInz6obpgDQGcFmaJgB",
        "Sam": "yoZ06aMxZJJ28mfd3POQ",
        # Custom voices from env
        "Cipher": os.getenv("ELEVENLABS_VOICE_CIPHER", ""),
        "Narrator": os.getenv("ELEVENLABS_VOICE_NARRATOR", ""),
    }

    return VOICE_IDS.get(voice_name, get_default_voice())


async def get_http_client() -> httpx.AsyncClient:
    """Get or create async HTTP client for streaming."""
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(timeout=120.0)
    return http_client


def use_streaming() -> bool:
    """Check if streaming mode is enabled."""
    return os.getenv("ELEVENLABS_USE_STREAMING", "false").lower() == "true"


async def text_to_speech_stream(
    text: str,
    voice: str = None,
    model: str = None
) -> AsyncIterator[str]:
    """
    Stream text-to-speech audio chunks using PCM streaming.

    Yields base64-encoded audio chunks as they're generated.
    Only works with local Chatterbox wrapper.

    Args:
        text: Text to convert to speech
        voice: Voice ID (default: from env)
        model: Model ID (ignored for local)

    Yields:
        Base64 encoded audio chunks (PCM -> WAV wrapped)
    """
    if not text or not text.strip():
        return

    base_url = os.getenv("ELEVENLABS_BASE_URL")
    if not base_url:
        # Fall back to non-streaming for real ElevenLabs
        result = await text_to_speech(text, voice, model)
        if result:
            yield result
        return

    voice_id = voice if voice else get_default_voice()
    model_id = model if model else get_model()

    print(f"[TTS Stream] Using model: {model_id}")

    # Strip tags
    clean_text = strip_action_tags(text)
    if not is_premium_model(model_id):
        clean_text = strip_all_tags(clean_text)
        print(f"[TTS Stream] Non-premium model - stripped all tags")

    if not clean_text:
        return

    # Call the PCM streaming endpoint
    url = f"{base_url}/v1/text-to-speech/{voice_id}/stream-pcm"

    client = await get_http_client()

    try:
        # PCM audio parameters (from Chatterbox)
        sample_rate = 24000
        channels = 1
        bits = 16

        pcm_chunks = []
        chunk_count = 0

        async with client.stream(
            "POST",
            url,
            json={"text": clean_text, "model_id": model_id},
            timeout=120.0
        ) as response:
            if response.status_code != 200:
                print(f"[TTS Stream] Error: {response.status_code}")
                # Fall back to non-streaming
                result = await text_to_speech(text, voice, model)
                if result:
                    yield result
                return

            # Chatterbox generates complete audio for the sentence
            # Collect all data and yield as one piece (no internal splits = no ghost noise)
            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk

            if buffer:
                duration_secs = len(buffer) / (sample_rate * 2)
                wav_data = pcm_to_wav(buffer, sample_rate, channels, bits)
                audio_base64 = base64.b64encode(wav_data).decode('utf-8')
                print(f"[TTS Stream] Complete: {len(buffer)} bytes PCM ({duration_secs:.1f}s)")
                yield audio_base64

    except Exception as e:
        import traceback
        print(f"[TTS Stream] Error: {e}")
        traceback.print_exc()
        # Fall back to non-streaming
        try:
            result = await text_to_speech(text, voice, model)
            if result:
                yield result
        except Exception as e2:
            print(f"[TTS Stream] Fallback also failed: {e2}")


def pcm_to_wav(pcm_data: bytes, sample_rate: int, channels: int, bits: int) -> bytes:
    """Convert raw PCM data to WAV format."""
    import struct

    # WAV header
    byte_rate = sample_rate * channels * (bits // 8)
    block_align = channels * (bits // 8)
    data_size = len(pcm_data)

    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,  # File size - 8
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1 size
        1,   # Audio format (PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b'data',
        data_size
    )

    return wav_header + pcm_data
