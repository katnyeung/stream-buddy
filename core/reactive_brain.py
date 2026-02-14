"""
Reactive Brain - Quick contextual filler on WAIT decisions.

Fires a fast Gemini Flash call to generate a short (~5-15 word) filler
response so the co-host feels alive during dead air. Only used when the
main brain decides WAIT.

Target latency: ~300-500ms LLM + ~300ms TTS = ~800ms total.
"""
import os
import logging
import time

from core.script_manager import get_client, strip_action_tags

logger = logging.getLogger(__name__)


async def generate_reactive_response(
    transcript: str,
    mood_hint: str = "friendly",
    gesture_hint: str = "nod",
    buddy_history: list[str] | None = None,
    section_titles: list[str] | None = None,
) -> str | None:
    """Generate a short reactive filler response using Gemini Flash.

    Args:
        transcript: Recent speaker transcript snippet.
        mood_hint: Mood from Stage 1 decision (e.g. "curious", "happy").
        gesture_hint: Gesture from Stage 1 (e.g. "nod", "think_hand").
        buddy_history: Last 2-3 buddy responses for repetition avoidance.
        section_titles: Script section titles for topic awareness.

    Returns:
        Tagged text like "[mood:curious] [head:tilt] Oh, interesting point!"
        or None on failure / repetition.
    """
    if not transcript or len(transcript.strip()) < 5:
        return None

    buddy_history = buddy_history or []
    section_titles = section_titles or []

    # Build ultra-minimal prompt (~200 tokens)
    recent_buddy = ""
    if buddy_history:
        recent = buddy_history[-3:]
        recent_buddy = f"\nDO NOT repeat: {' | '.join(h[:40] for h in recent)}"

    topics = ""
    if section_titles:
        topics = f"\nTopics: {', '.join(section_titles[:4])}"

    prompt = f"""You are Buddy, a stream co-host. The speaker just said something and you're listening.
Generate a SHORT filler reaction (5-15 words max). Be natural, like a real co-host nodding along.

Speaker: "{transcript[-200:]}"
Your mood: {mood_hint}{recent_buddy}{topics}

Rules:
- Start with [mood:{mood_hint}] and one gesture tag like [head:{gesture_hint}]
- 5-15 words ONLY. One short sentence.
- React to what they said - show you're listening
- NO questions. NO "let's move to". Just a brief acknowledgment/reaction.
- Examples: "Oh yeah, that's a solid approach!", "Hmm, the latency part is interesting!", "Right, makes total sense."

Output ONLY the tagged response text. Nothing else."""

    gemini = get_client()
    start = time.time()

    try:
        from google.genai import types

        response = await gemini.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=60,
            )
        )

        text = response.text.strip()
        llm_time = time.time() - start
        logger.info(f"[Reactive] LLM in {llm_time:.2f}s: '{text[:80]}'")

        if not text:
            return None

        # Simple repetition check against buddy_history
        text_clean = strip_action_tags(text).lower()
        for prev in buddy_history[-3:]:
            prev_clean = strip_action_tags(prev).lower() if prev else ""
            if not prev_clean:
                continue
            # Exact match
            if text_clean == prev_clean:
                logger.info(f"[Reactive] Skipped - exact repeat")
                return None
            # High word overlap
            text_words = set(text_clean.split())
            prev_words = set(prev_clean.split())
            if text_words and prev_words:
                overlap = len(text_words & prev_words) / max(len(text_words), len(prev_words))
                if overlap > 0.6:
                    logger.info(f"[Reactive] Skipped - {overlap:.0%} word overlap")
                    return None

        return text

    except Exception as e:
        logger.error(f"[Reactive] Error: {e}")
        return None
