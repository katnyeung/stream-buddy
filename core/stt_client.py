"""
Speech-to-Text client using OpenAI Whisper.
"""
import os
import re
import time
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global client
    if client is None:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return client


def _remove_hallucinations(text: str) -> str:
    """
    Remove common Whisper hallucination phrases.
    Whisper often hallucinates these during silence or low audio.
    """
    if not text:
        return ""

    result = text.strip()

    # Spam phrases that Whisper hallucinates (from training data)
    spam_phrases = [
        # FEMA spam
        "For more information visit www.fema.gov",
        "For more information, visit www.fema.gov",
        "For more information visit www.FEMA.gov",
        "www.fema.gov",
        "For more information",
        # UN spam
        "For more UN videos visit www.un.org",
        "www.un.org",
        # Social media URLs
        "HTTP://www.facebook.com",
        "http://www.facebook.com",
        "http://www.instagram.com",
        "www.facebook.com",
        "www.instagram.com",
        # Chinese media hallucinations
        "廣告後面有詳細內容,請搜尋【廣告】",
        "廣告後面有詳細內容",
        "請搜尋【廣告】",
        "MING PAO CANADA // MING PAO TORONTO",
        "MING PAO CANADA",
        "MING PAO TORONTO",
        "多謝您收睇時局新聞,再會!",
        "多謝您收睇",
        "再會!",
        # Stream/config text hallucinations
        "Casual chat, viewer interaction, tech topics",
        "Casual chat",
        "viewer interaction",
        "tech topics",
        "Q&A",
    ]

    # Remove all occurrences of spam phrases (case-insensitive)
    for phrase in spam_phrases:
        result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)

    # Clean up extra whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    # Whisper hallucination phrases (from YouTube training data)
    # These appear when audio has silence - NOT legitimate presenter phrases
    # Source: https://community.openai.com/t/whisper-hallucination-how-to-recognize-and-solve/218307
    hallucination_phrases_anywhere = [
        # YouTube ending phrases (very common hallucination)
        "Thank you for watching.",
        "Thanks for watching.",
        "Thank you for listening.",
        "Thanks for listening.",
        "Subscribe to my channel.",
        "Please subscribe.",
        "Like and subscribe.",
        "Don't forget to subscribe.",
        "Hit the like button.",
        "Ring the bell.",
        "See you in the next video.",
        "See you next time.",
        # Subtitle/caption artifacts
        "Subtitles by",
        "Sub by",
        "Translated by",
        "Transcribed by",
        # Music/sound placeholders
        "[Music]",
        "[Applause]",
        "[Laughter]",
        "(Music)",
        "(Applause)",
    ]

    # Remove hallucination phrases from anywhere in the text
    for phrase in hallucination_phrases_anywhere:
        result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)

    # Clean up extra whitespace after removals
    result = re.sub(r'\s+', ' ', result).strip()

    # Phrases that are hallucinations ONLY at the END (not if said mid-sentence)
    hallucination_endings = [
        "Thank you.",
        "Thanks.",
        "Bye bye.",
        "Bye.",
        "Goodbye.",
    ]

    # Single word hallucinations at the end
    single_word_endings = ["you", "You", "bye", "Bye"]

    # Remove phrase hallucinations from the end
    for phrase in hallucination_endings:
        if result.endswith(phrase):
            result = result[:-len(phrase)].strip()

    # Remove single word hallucinations from the end
    for word in single_word_endings:
        patterns = [f" {word}", f". {word}", f"? {word}", f"! {word}"]
        for pattern in patterns:
            if result.endswith(pattern):
                result = result[:-len(pattern)].strip()
                break

    # Remove repeated phrases
    result = _remove_repetitions(result)

    return result.strip()


def _remove_repetitions(text: str) -> str:
    """Remove repeated phrases that Whisper sometimes generates."""
    if not text or len(text) < 20:
        return text

    result = text

    # === Sentence-level deduplication (most effective for Whisper hallucinations) ===
    # Split into sentences and remove duplicates while preserving order
    sentences = re.split(r'(?<=[.!?])\s+', result)
    if len(sentences) > 2:
        seen = set()
        unique_sentences = []
        for s in sentences:
            s_clean = s.strip()
            s_normalized = s_clean.lower()
            if s_normalized and s_normalized not in seen:
                seen.add(s_normalized)
                unique_sentences.append(s_clean)

        # If we removed more than half the sentences, it was likely repetitive hallucination
        if len(unique_sentences) < len(sentences) * 0.6:
            result = ' '.join(unique_sentences)
            logger.info(f"[STT] Removed {len(sentences) - len(unique_sentences)} duplicate sentences")

    # Catch longer repeated phrases (10-150 chars) repeated 2+ times
    # e.g., "I'm Cassandra. I'm a software engineer. I'm Cassandra. I'm a software engineer."
    result = re.sub(r'(.{10,150}?)\s*\1(?:\s*\1)*', r'\1', result)

    # Catch sentence-level repetitions with "So, let's get started" patterns
    result = re.sub(r'((?:So,?\s*)?let\'s get started\.?\s*)+', "Let's get started. ", result, flags=re.IGNORECASE)

    # Remove excessive word/phrase repetitions (any language)
    result = re.sub(r'(\S+)(?:[,，、\s]+\1){2,}', r'\1', result)

    # Catch repeated characters/words without separators
    result = re.sub(r'(.{1,6}?)\1{3,}', r'\1', result)

    # Catch "tech topics, tech topics, tech topics" pattern
    result = re.sub(r'(tech topics[,\s]*){2,}', 'tech topics', result, flags=re.IGNORECASE)

    # Catch any "X, X, X, X" pattern (same phrase repeated with comma)
    result = re.sub(r'([^,]{3,30}),(\s*\1,?){2,}', r'\1', result)

    # Catch "I'm X. I'm a Y. And I'm here to..." repeated patterns
    result = re.sub(r'(I\'m \w+\.\s*I\'m a \w+[^.]*\.\s*And I\'m here[^.]*\.?\s*)+', r'\1', result, flags=re.IGNORECASE)

    # === Word-level deduplication at the end ===
    words = result.split()
    if len(words) < 6:
        return result

    # Check for repeated sequences at the end (word-level)
    for seq_len in range(3, min(10, len(words) // 2)):
        end_seq = words[-seq_len:]
        prev_seq = words[-2*seq_len:-seq_len]
        if end_seq == prev_seq:
            words = words[:-seq_len]

    return " ".join(words)


async def transcribe_audio(filepath: str, context_prompt: str = "") -> str:
    """
    Transcribe audio file using OpenAI Whisper.

    Args:
        filepath: Path to audio file (WebM, MP3, etc.)
        context_prompt: Optional context for better accuracy

    Returns:
        Transcribed text
    """
    if not os.path.exists(filepath):
        logger.warning(f"[STT] File not found: {filepath}")
        return ""

    file_size = os.path.getsize(filepath)
    if file_size < 10000:  # Skip files less than 10KB (Whisper needs ~0.5s of audio minimum)
        logger.debug(f"[STT] File too small: {file_size} bytes, skipping")
        return ""

    logger.info(f"[STT] Transcribing {file_size} bytes...")
    start = time.time()

    client = get_client()

    try:
        with open(filepath, "rb") as audio_file:
            audio_content = audio_file.read()

            from io import BytesIO
            audio_bytes = BytesIO(audio_content)
            audio_bytes.name = "audio.webm"

            api_start = time.time()
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_bytes,
                prompt=context_prompt,
                temperature=0.0,  # Deterministic - reduces hallucinations
                language="en"
            )
            api_time = time.time() - api_start
            logger.info(f"[STT] Whisper API call: {api_time:.2f}s")

        text = response.text if hasattr(response, 'text') else ""

        # Check for abnormally long transcript (hallucination indicator)
        # Normal speech is ~2-3 words/second, audio is ~10KB/second
        # If we get 50+ words from <50KB audio, it's suspicious
        word_count = len(text.split()) if text else 0
        expected_max_words = max(20, file_size // 2000)  # ~2 words per 2KB
        if word_count > expected_max_words * 2:
            logger.warning(f"[STT] Suspicious transcript: {word_count} words from {file_size} bytes (expected max ~{expected_max_words})")
            # Truncate to reasonable length
            words = text.split()[:expected_max_words]
            text = ' '.join(words)
            logger.info(f"[STT] Truncated to {len(words)} words")

        # Post-process to remove hallucinations
        original_len = len(text)
        text = _remove_hallucinations(text)

        if original_len != len(text):
            logger.info(f"[STT] Filtered hallucinations: {original_len} -> {len(text)} chars")

        total_time = time.time() - start
        logger.info(f"[STT] Total time: {total_time:.2f}s, result: '{text[:80]}...' " if len(text) > 80 else f"[STT] Total: {total_time:.2f}s, result: '{text}'")

        return text

    except Exception as e:
        logger.error(f"[STT] Transcription error: {e}")
        return ""
    finally:
        # Clean up temp file
        try:
            os.unlink(filepath)
        except:
            pass
