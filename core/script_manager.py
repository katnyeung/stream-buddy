"""
Script manager - parses and tracks script progress using Gemini.
"""
import json
import os
import re
from google import genai
from google.genai import types


def clean_json_response(text: str) -> str:
    """Clean LLM response to extract valid JSON."""
    original = text
    text = text.strip()

    # Remove markdown code blocks
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    # Try to extract JSON object with regex
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        text = json_match.group()

    # Fix common issues: newlines inside strings
    text = text.replace('\n', ' ').replace('\r', '')

    # Fix multiple spaces
    text = re.sub(r'\s+', ' ', text)

    # Try to parse, if fails log the raw response
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        print(f"JSON parse failed: {e}")
        print(f"Raw response: {original[:500]}")
        print(f"Cleaned: {text[:500]}")

    return text.strip()


from core.redis_client import (
    store_script, get_script,
    store_script_structure, get_script_structure,
    store_session_state, get_session_state
)

client = None


def get_client():
    global client
    if client is None:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return client


async def parse_script(session_id: str, raw_script: str) -> dict:
    """
    Parse raw script into structured sections using Gemini.
    Returns structure with sections, key points, and flow.
    """
    await store_script(session_id, raw_script)

    client = get_client()

    prompt = f"""Analyze this script/outline for a live stream presentation.
Break it down into sections that a speaker would follow.

Script:
{raw_script}

Return a JSON object with this structure:
{{
    "title": "main topic",
    "sections": [
        {{
            "id": 1,
            "title": "section title",
            "key_points": ["point 1", "point 2"],
            "suggested_phrases": ["how to start this section"],
            "duration_hint": "short/medium/long"
        }}
    ],
    "total_sections": number
}}

Only return valid JSON, no markdown."""

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",  # or "gemini-2.0-flash-exp" for cheaper
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2000
            )
        )

        text = clean_json_response(response.text)
        structure = json.loads(text)
        await store_script_structure(session_id, structure)

        # Initialize session state
        initial_state = {
            "current_section": 0,
            "covered_points": [],
            "transcript_history": []
        }
        await store_session_state(session_id, initial_state)

        return structure

    except Exception as e:
        print(f"Script parse error: {e}")
        # Fallback simple structure
        structure = {
            "title": "Script",
            "sections": [{"id": 1, "title": "Main", "key_points": [raw_script[:200]], "suggested_phrases": [], "duration_hint": "medium"}],
            "total_sections": 1
        }
        await store_script_structure(session_id, structure)

        # Initialize session state (was missing!)
        initial_state = {
            "current_section": 0,
            "covered_points": [],
            "transcript_history": []
        }
        await store_session_state(session_id, initial_state)

        return structure


async def analyze_progress(session_id: str, transcript: str, style: str = "balanced", personality: str = "neutral", supports_emotions: bool = False) -> dict:
    """
    Analyze current transcript and decide co-host action.

    Actions:
        - enrich: Add value to speaker's point (verbal)
        - remind: Suggest next topic (visual only)
        - respond: Answer direct question (verbal)
        - wait: Stay quiet, let speaker flow
    """
    structure = await get_script_structure(session_id)
    state = await get_session_state(session_id)

    if not structure or not state:
        return {"action": "wait", "prompt_text": "", "speak_text": "", "reason": "no script loaded"}

    # Add transcript to history
    state["transcript_history"].append(transcript)
    if len(state["transcript_history"]) > 20:
        state["transcript_history"] = state["transcript_history"][-20:]

    # Track what Buddy has already said (don't repeat)
    buddy_history = state.get("buddy_history", [])

    # Track if we're in a conversation (Buddy just spoke)
    in_conversation = state.get("in_conversation", False)

    client = get_client()

    # Build script summary with section IDs for tracking
    section_titles = []
    script_summary = []
    for i, s in enumerate(structure.get("sections", [])):
        section_titles.append(s['title'])
        points = s.get("key_points", [])[:3]
        script_summary.append(f"[{i+1}] {s['title']}: {', '.join(points)}")

    # Build buddy history string - make it prominent
    buddy_said = ""
    if buddy_history:
        buddy_said = f"""

⚠️ WHAT YOU ALREADY SAID (DO NOT REPEAT THESE POINTS):
{chr(10).join(f'- "{h}"' for h in buddy_history[-5:])}

Pick a DIFFERENT angle if you enrich. Don't repeat VM, sandbox, orchestration if you already said it."""

    # Conversation mode context
    conversation_context = ""
    if in_conversation and buddy_history:
        last_buddy_said = buddy_history[-1] if buddy_history else ""
        conversation_context = f"""

CONVERSATION MODE ACTIVE - You just said: "{last_buddy_said}"
Analyze the speaker's response:
- If they're ENGAGING with your point (agreeing, building on it, asking about it) → You can add ONE brief follow-up, then wait
- If they've moved to a NEW topic → Just WAIT and listen
- Don't force continuation - let them lead"""

    # Style-specific instructions
    style_instructions = ""
    if style == "aggressive":
        style_instructions = """
STYLE: AGGRESSIVE - Jump in often! React to names, companies, products, numbers."""
    elif style == "passive":
        style_instructions = """
STYLE: PASSIVE - Only respond when asked directly."""
    else:  # balanced
        style_instructions = """
STYLE: BALANCED - Enrich key points, wait when speaker is flowing."""

    # Personality-specific instructions
    personality_instructions = ""
    if personality == "positive":
        personality_instructions = """
PERSONALITY: SUPPORTIVE
- Agree and build on speaker's points
- Be encouraging: "Great point!", "Exactly right!"
- Add facts that SUPPORT their argument
- Find the positive angle
- Help them look good"""
    elif personality == "critical":
        personality_instructions = """
PERSONALITY: SKEPTICAL ANALYST
- Question the NEWS and CLAIMS, not the speaker personally
- Challenge valuations: "$2B for Manus AI - is that justified? What's their actual revenue?"
- Question strategic fit: "Does Meta really need this? They already have..."
- Think ahead to problems: "What happens when competitors copy this?"
- Use DATA to challenge: "But OpenAI raised $10B, so $2B seems cheap/expensive..."
- Ask "why" and "how": "How will they integrate this with existing Meta AI?"
- Point out risks: "What if the Manus AI team leaves after acquisition?"
- Example: "Two billion sounds big, but compared to what Meta spends on VR..."
- Example: "Sure it works now, but can it scale to Meta's billion users?"
- Be the smart skeptic in the room, not negative"""
    else:  # neutral
        personality_instructions = """
PERSONALITY: NEUTRAL - Balanced perspective, add facts without strong opinion."""

    # Emotion instructions for premium TTS model
    emotion_instructions = ""
    if supports_emotions:
        emotion_instructions = """
EXPRESSIVE SPEECH: Premium TTS enabled - be DRAMATIC and expressive!

EMOTIONS TO USE:
- EXCITEMENT: "Wow!", "Oh!", "This is huge!", "No way!", "Holy—"
- SURPRISE: "Wait, what?", "Woah!", "Hang on...", "Did you just say...?"
- SKEPTICISM: "Hmm...", "Really?", "I don't know about that...", "But wait..."
- ENTHUSIASM: "Yes!", "Exactly!", "Love it!", "That's brilliant!"
- THOUGHTFUL: "Interesting...", "So...", "Actually...", "You know what..."
- DRAMATIC PAUSE: Use "..." for suspense, "—" for interruption

VOICE TECHNIQUES:
- Start sentences with emotional reactions
- Use longer pauses (......) for dramatic effect
- Vary sentence length - short punchy! Then longer explanations.
- Questions raise pitch naturally?
- Exclamations carry energy!

EXAMPLE OUTPUTS:
- "Wow! Two billion dollars? ...That's... that's actually a lot less than I expected!"
- "Oh— interesting! So they're betting big on this, huh?"
- "Hmm... I don't know. That sounds risky to me..."
- "Wait wait wait— did you just say they're replacing the whole team?!"""

    prompt = f"""You are Buddy, co-host on a tech stream.
{style_instructions}
{personality_instructions}
{emotion_instructions}

TOPIC: {section_titles}
{buddy_said}

SPEAKER JUST SAID: "{transcript}"

ACTION PRIORITY:
1. RESPOND if speaker asks: "what do you think", "help me", "conclusion", "buddy", "any opinion"
2. ENRICH only if you have a SPECIFIC NEW fact (not generic)
3. WAIT if nothing new to add

BANNED PHRASES (do not use):
- "could also"
- "automation could"
- "potential impact"
- "streamline"
- Starting with product name then generic statement

GOOD enrichments (specific):
- "DeepSeek trained for $5M vs OpenAI's $100M"
- "Yann LeCun won the Turing Award in 2018"
- "Meta spent $40B on AI last year"

BAD enrichments (generic):
- "Manus AI's automation could help Meta..."
- "This could streamline their workflow..."

JSON: {{"action": "respond|enrich|wait", "speak_text": "response", "sections_covered": [1], "reason": "why"}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",  # More stable than preview
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1000,
                response_mime_type="application/json"  # Force JSON output
            )
        )

        text = clean_json_response(response.text)
        result = json.loads(text)

        # Save what Buddy said to avoid repetition
        if result.get("action") in ["enrich", "respond"] and result.get("speak_text"):
            speak_text = result["speak_text"]

            # CHECK FOR REPETITION - block if too similar to recent history
            if "buddy_history" not in state:
                state["buddy_history"] = []

            # Check for exact or near-exact match
            is_repetition = False
            speak_lower = speak_text.lower()
            for prev in state["buddy_history"]:
                prev_lower = prev.lower()
                # Exact match
                if speak_lower == prev_lower:
                    is_repetition = True
                    break
                # High overlap (>70% words match)
                speak_words = set(speak_lower.split())
                prev_words = set(prev_lower.split())
                if len(speak_words) > 0 and len(prev_words) > 0:
                    overlap = len(speak_words & prev_words) / max(len(speak_words), len(prev_words))
                    if overlap > 0.7:
                        is_repetition = True
                        break

            # Also block overused phrases
            overused_patterns = [
                "manus ai's automation could",
                "could also",
                "that's right. manus",
                "indeed. manus",
                "interesting. manus",
                "absolutely. manus",
            ]
            for pattern in overused_patterns:
                if pattern in speak_lower:
                    is_repetition = True
                    break

            if is_repetition:
                print(f"[BLOCKED REPETITION] '{speak_text[:50]}...'")
                result["action"] = "wait"
                result["speak_text"] = ""
                result["reason"] = "blocked - too similar to previous response"
            else:
                state["buddy_history"].append(speak_text)
                # Keep only last 10
                if len(state["buddy_history"]) > 10:
                    state["buddy_history"] = state["buddy_history"][-10:]
                # Enter conversation mode
                state["in_conversation"] = True
        else:
            # Exit conversation mode when waiting or reminding
            state["in_conversation"] = False

        await store_session_state(session_id, state)
        return result

    except Exception as e:
        print(f"Progress analysis error: {e}")
        return {
            "action": "wait",
            "prompt_text": "",
            "speak_text": "",
            "topics_covered": [],
            "reason": f"error: {e}"
        }


async def get_current_prompt(session_id: str) -> str:
    """Get the current suggested prompt text for the speaker."""
    structure = await get_script_structure(session_id)
    state = await get_session_state(session_id)

    if not structure or not state:
        return ""

    section_idx = min(state["current_section"], len(structure["sections"]) - 1)
    section = structure["sections"][section_idx]

    if section.get("suggested_phrases"):
        return section["suggested_phrases"][0]
    elif section.get("key_points"):
        return section["key_points"][0]

    return section.get("title", "")
