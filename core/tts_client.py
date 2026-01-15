"""
Text-to-Speech client using ElevenLabs.
"""
import os
import re
import base64
from elevenlabs import ElevenLabs

client: ElevenLabs | None = None


def get_client() -> ElevenLabs:
    global client
    if client is None:
        client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
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


def strip_action_tags(text: str) -> str:
    """Remove VTuber action tags - these are for avatar control, not TTS."""
    # Remove VTuber control tags like [mood:X], [gesture:Y], [head:Z,repeat:2,delay:500], etc.
    return re.sub(r'\[(?:mood|gesture|action|eye|head|body|brow):\w+(?:,[^\]]+)?\]', '', text).strip()


def strip_all_tags(text: str) -> str:
    """Remove ALL bracketed tags for models that don't support them."""
    return re.sub(r'\[.*?\]', '', text).strip()


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

    # Strip VTuber action tags (mood, gesture, head, etc.) - TTS doesn't need them
    clean_text = strip_action_tags(text)

    if not clean_text:
        return ""

    client = get_client()

    try:
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
