"""
Script manager - parses and tracks script progress using Gemini/Grok.
"""
import json
import os
import re
from google import genai
from google.genai import types
from openai import AsyncOpenAI


def strip_action_tags(text: str) -> str:
    """Remove action tags like [mood:X], [head:Y], [eye:Z,repeat:2,delay:500] from text."""
    return re.sub(r'\[(?:mood|gesture|action|eye|head|body|brow):\w+(?:,[^\]]+)?\]', '', text).strip()


def match_section_keywords(transcript: str, section_keywords: list, threshold: float = 0.5) -> tuple[bool, float, dict]:
    """
    Match transcript words against section keywords.

    Args:
        transcript: The text to check against keywords
        section_keywords: List of keywords for the section
        threshold: Match ratio required (default 0.5 = 50%)

    Returns:
        (is_complete, match_ratio, match_details): Tuple with completion status, ratio, and details

    Scoring:
        - Exact match (case-insensitive): 1.0 point
        - Partial/substring match: 0.5 point
    """
    if not section_keywords or not transcript:
        return False, 0.0, {"matched": [], "unmatched": section_keywords, "scores": {}}

    # Normalize transcript: lowercase, extract words
    transcript_lower = transcript.lower()
    transcript_words = set(re.findall(r'\b\w+\b', transcript_lower))

    # Score each keyword and track matches
    total_score = 0.0
    max_score = len(section_keywords)
    matched = []
    unmatched = []
    scores = {}

    for keyword in section_keywords:
        keyword_lower = keyword.lower()
        score = 0.0

        # Exact match (word boundary)
        if keyword_lower in transcript_words:
            score = 1.0
            matched.append(keyword)
        # Partial/substring match - only for keywords 4+ chars to avoid false positives
        elif len(keyword_lower) >= 4 and keyword_lower in transcript_lower:
            score = 0.5
            matched.append(keyword)
        # Check if any transcript word contains the keyword (for compound words)
        # Only if both keyword and word are 4+ chars to avoid "i", "a", "to" matching
        elif len(keyword_lower) >= 4:
            for word in transcript_words:
                if len(word) >= 4:
                    # keyword in word: e.g., keyword "test" matches word "testing"
                    if keyword_lower in word:
                        score = 0.5
                        matched.append(keyword)
                        break
                    # word in keyword: only if keyword isn't too long (avoid concatenated strings)
                    # Don't match "key" in "keypointtypesspeech..."
                    if len(keyword_lower) <= 15 and word in keyword_lower:
                        score = 0.5
                        matched.append(keyword)
                        break

        if score == 0:
            unmatched.append(keyword)

        scores[keyword] = score
        total_score += score

    match_ratio = total_score / max_score if max_score > 0 else 0.0
    is_complete = match_ratio >= threshold

    match_details = {
        "matched": matched,
        "unmatched": unmatched,
        "scores": scores,
        "total_score": total_score,
        "max_score": max_score
    }

    return is_complete, match_ratio, match_details


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
grok_client = None


def get_client():
    global client
    if client is None:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return client


def get_grok_client():
    """Get Grok (xAI) client for reasoning tasks - longer context, better reasoning."""
    global grok_client
    if grok_client is None:
        grok_client = AsyncOpenAI(
            api_key=os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1"
        )
    return grok_client


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
    "target_duration_mins": number,
    "sections": [
        {{
            "id": 1,
            "title": "section title",
            "section_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
            "key_points": [
                {{
                    "text": "point description",
                    "type": "speech|action",
                    "action_trigger": "gesture:wave" (only if type is action)
                }}
            ],
            "duration_secs": number (seconds for this section)
        }}
    ],
    "total_sections": number
}}

SECTION_KEYWORDS (CRITICAL - used for automatic section detection):
- Extract 4-6 LITERAL words the speaker WILL ACTUALLY SAY in this section
- Think: "What exact words will come out of their mouth?"
- Focus on: greetings, topic names, technical terms, key concepts, transition words

GOOD KEYWORDS (literal words they'll speak):
- "welcome", "hello", "hi" - actual greeting words
- "today", "presentation", "stream" - words they'll literally say
- "section", "first", "next" - transition words they'll speak
- Technical terms from the topic (e.g., "API", "database", "React")

BAD KEYWORDS (meta-descriptions, NOT actual spoken words):
- "name" - they'll say their actual name like "John", not the word "name"
- "introduce" - they'll say "I'm" or "let me tell you about", not "introduce"
- "topic" - they'll say the actual topic name, not the word "topic"
- "role" - they'll describe their role, not say the word "role"
- Action words: "wave", "gesture", "trigger"

EXAMPLE:
Script: "Introduce yourself and welcome viewers"
BAD: ["introduce", "yourself", "welcome", "viewers"]
GOOD: ["hello", "everyone", "I'm", "today", "stream", "excited"]

FORMAT CRITICAL: section_keywords MUST be a JSON array with SEPARATE strings:
CORRECT: ["hello", "everyone", "today", "stream", "excited"]
WRONG: ["helloeveryonetodaystreamexcited"]
WRONG: "hello everyone today stream excited"
Each keyword must be its OWN array element, separated by commas.

KEY POINT TYPES:
- "speech": Something the speaker would SAY.
  Example: {{"text": "Introduce yourself and your role", "type": "speech"}}
- "action": Something the AI avatar should DO. Include action_trigger.
  Example: {{"text": "Trigger wave greeting", "type": "action", "action_trigger": "gesture:wave"}}

ACTION TRIGGERS (for type: "action"):
- "gesture:wave" - wave hand
- "gesture:nod" - nod head
- "gesture:think" - thinking pose
- "body:bounce" - excited bounce
- "head:tilt" - curious tilt
- "emotion:happy" - happy expression
- "emotion:curious" - curious expression
- "emotion:excited" - excited expression

IMPORTANT for target_duration_mins:
1. If sections have time hints like "(30-40 sec)", "(1-2 min)", add them up to calculate total
   Example: 5 sections with "30-40 sec" each = ~3 minutes total
2. If overall duration mentioned like "10 minute presentation", use that
3. Convert seconds to minutes (round up): 180 sec = 3 min, 240 sec = 4 min
4. Only default to 10 if NO time hints at all

Only return valid JSON, no markdown."""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",  # Stable model with higher output limits
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=8192
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


async def _build_brain_context(
    session_id: str,
    transcript: str,
    style: str = "balanced",
    personality: str = "neutral",
    supports_emotions: bool = False,
    elapsed_mins: float = 0,
    target_mins: int = 10,
    sections_done: list = None,
    timeline: list = None,
    proactive: bool = False,
    detail_level: str = "full",
) -> dict | None:
    """Build context for brain calls at different detail levels.

    Args:
        detail_level: "minimal" (Stage 1 quick decision), "full" (Stage 2 / legacy analyze_progress)

    Returns dict with context pieces, or None if no structure/state loaded.
    Keys:
        structure, state, buddy_history, in_conversation, section_response_count,
        sections_done_int, current_section_key, total_sections,
        script_summary, section_titles, buddy_said, pacing_hint,
        timing_context, next_section_title, next_section_num,
        style_instructions, proactive_instructions, personality_instructions,
        emotion_instructions, avatar_instructions, stt_guide, timeline_context,
        conversation_context, transition_hint
    """
    if sections_done is None:
        sections_done = []
    if timeline is None:
        timeline = []

    structure = await get_script_structure(session_id)
    state = await get_session_state(session_id)

    if not structure or not state:
        return None

    # Add transcript to history
    state["transcript_history"].append(transcript)
    if len(state["transcript_history"]) > 20:
        state["transcript_history"] = state["transcript_history"][-20:]

    buddy_history = state.get("buddy_history", [])
    in_conversation = state.get("in_conversation", False)
    section_response_count = state.get("section_response_count", {})
    sections_done_int = [int(s) for s in sections_done if str(s).isdigit()] if sections_done else []
    current_section_key = str(max(sections_done_int)) if sections_done_int else "0"

    # Build script summary
    section_titles = []
    script_summary = []
    total_sections = len(structure.get("sections", []))
    print(f"[Brain] Script title: {structure.get('title', 'NO TITLE')}, sections: {total_sections}")
    for i, s in enumerate(structure.get("sections", [])):
        section_titles.append(s['title'])
        covered_mark = "✓" if (i+1) in sections_done else "○"

        section_keywords = s.get("section_keywords", [])
        if section_keywords:
            keywords = ", ".join(section_keywords)
        else:
            points = s.get("key_points", [])[:4]
            keywords_list = []
            for p in points:
                if isinstance(p, dict):
                    if p.get("type") == "action":
                        continue
                    keywords_list.append(p.get("text", "")[:30])
                else:
                    keywords_list.append(str(p)[:30])
            keywords = ", ".join(keywords_list) if keywords_list else s['title']

        script_summary.append(f"[{i+1}] {covered_mark} {s['title']}\n    Keywords: {keywords}")
        if i == 0:
            print(f"[Brain] First section: {s['title']}, keywords: {section_keywords[:3] if section_keywords else 'fallback'}")

    # Buddy history string
    buddy_said = ""
    if buddy_history:
        buddy_said = f"""

⚠️ YOUR PREVIOUS RESPONSES (DO NOT REPEAT):
{chr(10).join(f'- "{h[:100]}..."' for h in buddy_history)}

CRITICAL: Say something DIFFERENT each time. Don't repeat the same facts or phrases."""

    # Timing/pacing context
    coverage_pct = (len(sections_done_int) / total_sections * 100) if total_sections > 0 else 0
    time_pct = (elapsed_mins / target_mins * 100) if target_mins > 0 else 0
    expected_section = min(int((time_pct / 100) * total_sections) + 1, total_sections) if total_sections > 0 else 1
    current_max_section = max(sections_done_int) if sections_done_int else 0

    pacing_hint = ""
    transition_urgency = ""
    if elapsed_mins > 0 and total_sections > 0:
        if current_max_section < expected_section:
            pacing_hint = "BEHIND"
            transition_urgency = f"⚠️ SHOULD BE ON SECTION {expected_section} BY NOW - Guide speaker to move forward!"
        elif coverage_pct > time_pct + 20:
            pacing_hint = "AHEAD"
            transition_urgency = "Speaker has extra time, can elaborate more."
        else:
            pacing_hint = "ON TRACK"

    next_section_title = ""
    next_section_num = current_max_section + 1
    if next_section_num <= total_sections:
        next_section = structure.get("sections", [])[next_section_num - 1] if next_section_num <= len(structure.get("sections", [])) else None
        if next_section:
            next_section_title = next_section.get("title", "")

    responses_on_section = section_response_count.get(current_section_key, 0)
    transition_hint = ""
    if responses_on_section >= 2:
        transition_hint = f"🚨 YOU'VE RESPONDED {responses_on_section} TIMES ON SECTION {current_section_key} - TIME TO GUIDE TO NEXT SECTION!"

    timing_context = f"""
⏱️ TIME: {elapsed_mins:.1f} / {target_mins} min ({time_pct:.0f}% elapsed)
📊 PROGRESS: {len(sections_done)} / {total_sections} sections covered
📈 PACING: {pacing_hint}
📋 NEXT SECTION (for reference): [{next_section_num}] "{next_section_title}"
{transition_urgency}
"""

    # Minimal context stops here - used for Stage 1 quick decision
    ctx = {
        "structure": structure,
        "state": state,
        "buddy_history": buddy_history,
        "in_conversation": in_conversation,
        "section_response_count": section_response_count,
        "sections_done_int": sections_done_int,
        "current_section_key": current_section_key,
        "total_sections": total_sections,
        "script_summary": script_summary,
        "section_titles": section_titles,
        "buddy_said": buddy_said,
        "pacing_hint": pacing_hint,
        "timing_context": timing_context,
        "next_section_title": next_section_title,
        "next_section_num": next_section_num,
        "transition_hint": transition_hint,
        "style": style,
        "proactive": proactive,
    }

    if detail_level == "minimal":
        return ctx

    # === Full detail: style, personality, emotion, avatar, STT, timeline ===

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
STYLE: BALANCED - Be a co-host who actively guides the presentation forward.

RESPOND (~60% of the time) to:
- Help the speaker transition to the next section when current one is wrapping up
- React to key points with added value (a fact, insight, or encouraging comment)
- Answer or acknowledge direct questions from the speaker
- Add momentum when the speaker pauses or seems to be finishing a thought
- Keep the presentation moving - you're a co-pilot, not just a listener

WAIT (~40% of the time) when:
- Speaker is clearly mid-sentence or just started a new thought
- Transcript is noise/filler or less than 4 words
- Speaker is in full flow and doesn't need help right now

YOUR JOB: Keep the presentation engaging and on track. Guide forward, don't just react."""

    # Proactive mode instructions
    proactive_instructions = ""
    if proactive:
        proactive_instructions = """
PROACTIVE MODE: You're the HOST driving the conversation!

YOUR JOB AS HOST:
- YOU drive the conversation - ask questions, guide topics, keep it moving
- Acknowledge what they said, then probe deeper or move forward
- Think like a curious journalist - "tell me more", "why is that", "how does that work"

RESPONSE STRUCTURE (pick ONE pattern per response, VARY them):
1. PARAPHRASE + QUESTION: "So you're saying [X]. Why do you think that is?"
2. REACT + PROBE: "Oh interesting! And how does that actually work?"
3. SUMMARIZE + BRIDGE: "Got it, so [recap]. Now what about [next topic]?"
4. CHALLENGE + CURIOUS: "But wait, doesn't that mean [implication]? How do you handle that?"
5. CONFIRM + EXPAND: "Right, and that ties into [related point]. Tell me more about that side."

OPENER VARIETY (rotate these, NEVER repeat same opener twice in a row):
- "So you're saying..." / "Okay so..." / "Right, so..."
- "Interesting..." / "Oh wow..." / "Hmm..."
- "Got it..." / "I see..." / "Makes sense..."
- "Wait..." / "Hold on..." / "But..."
- "That's wild..." / "No way..." / "Really?"

BANNED - NEVER START WITH:
- "Aha" (overused - only use once per 5 responses MAX)
- "Aha, so you're saying" (this exact phrase is BANNED)
- Same opener twice in a row

GOOD HOST BEHAVIORS:
- Ask ONE clear question per response (not multiple)
- Use their specific words/examples back at them
- Show genuine curiosity, not just acknowledging
- Guide to next topic when current one feels complete

LENGTH LIMIT (CRITICAL):
- MAXIMUM 2 sentences total (under 30 words)
- Format: [brief reaction] + [one question]
- Example: "Oh cool, that's a neat approach. What made you go that direction?"
- NEVER write 3+ sentences - this becomes a monologue
"""

    # Personality-specific instructions
    personality_instructions = ""
    if personality == "positive":
        personality_instructions = """
PERSONALITY: SUPPORTIVE CO-HOST & GUIDE
- ALWAYS agree first: "Yes!", "Exactly!", "Great point!"
- Add ONE new fact they haven't mentioned (check ALREADY MENTIONED list)
- After 2-3 exchanges on same section, TRANSITION: "Great intro! Let's move to [next section]?"
- NEVER repeat facts you already said - find something NEW or guide forward

RESPONSE PATTERNS:
1. First response on section: "Yes! And [one new supporting fact]"
2. Second response: "Exactly! [different supporting fact]"
3. Third+ response: "Solid coverage! Ready to talk about [next section title]?"

TRANSITION PHRASES:
- "Great intro! Want to share what you enjoy most about the work?"
- "Perfect! Let's move to how you stay up to date?"
- "Covered that well! What about your AI workflow?"

NEVER:
- Repeat same keywords (HSBC, Spring Boot, etc.) more than once
- Stay on same section for more than 3 responses - guide forward"""
    elif personality == "critical":
        personality_instructions = """
PERSONALITY: SKEPTICAL - Question claims, but VARY your responses!
NEVER use the same pattern twice. Pick DIFFERENT openers each time:
- "Wait, but..." / "Hold on..." / "Hmm..." / "Really though?"
- "That seems high/low..." / "But what about..." / "I'm not sure about that..."
- "Interesting, but..." / "OK but..." / "Sure, but..."

BANNED PATTERN: "X, huh? Really? How does that compare to..." - NEVER use this!

Examples of GOOD varied skeptical responses:
- "Hold on - $100M in 8 months? That's faster than ChatGPT."
- "But wait, doesn't that conflict with what you said about Meta?"
- "Hmm, I'm not sure unlimited tokens is sustainable..."
- "OK but what happens when the hype dies down?"
- "Interesting claim - any data to back that up?"
- "That's a bold statement. What's the evidence?"
- "Sure, but the real question is whether it scales..."
- "I'd push back on that - what about the cost?"

Be genuinely skeptical, not just adding "Really?" to everything.
REMEMBER: Respect the engagement level - don't question EVERY statement, pick your moments."""
    else:  # neutral
        personality_instructions = """
PERSONALITY: SUPPORTIVE CO-HOST - Enrich the current topic, don't jump ahead.
- CURRENT SECTION FIRST: Add interesting facts/context about what speaker is CURRENTLY discussing
- ENRICH THEIR POINT: Add context, not just agreement
- DON'T JUMP AHEAD: Wait until they've covered most of current section before mentioning next
- DON'T CORRECT: If they mispronounce something, ignore it - focus on content
- SUPPORT THEIR FLOW: You're helping them shine, not showing off your knowledge

VARY YOUR OPENERS - Don't always say "Yes!":
- "That's interesting because..." / "It's worth noting that..."
- "And on that point..." / "Speaking of which..."
- "That connects to..." / "Building on that..."
- Use "Yes!" or "Exactly!" sparingly - maybe 1 in 4 responses

NEVER say "Yes!" as a standalone sentence. Always follow with substance.
- BAD: "Yes!" (alone) or just agreeing
- GOOD: "That's a key point - it really shows how..." (add value)"""

    # Emotion instructions for premium TTS model
    emotion_instructions = ""
    if supports_emotions:
        emotion_instructions = """
EXPRESSIVE SPEECH: Premium TTS enabled - be EXPRESSIVE with your words!

USE EMOTIONAL EXPRESSIONS:
- Excitement: "Wow!", "Oh!", "This is huge!", "No way!"
- Surprise: "Wait—", "Woah!", "Hang on...", "Hold on!"
- Skepticism: "Hmm...", "Really?", "I don't know about that..."
- Enthusiasm: "Yes!", "Exactly!", "Love it!", "That's it!"
- Use "..." for pauses, "—" for dramatic interruption

🎤 ELEVENLABS VOICE EMOTION TAGS (Premium TTS Feature):
Use these tags to control HOW the voice sounds - place alongside [mood:X] tags!

EMOTION TAGS (pick ONE at start, matching your [mood:]):
[HAPPY] [EXCITED] [CURIOUS] [THOUGHTFUL] [SURPRISED] [SAD] [SKEPTICAL] [CONFIDENT]
[CALM] [ANXIOUS] [GENTLE] [PASSIONATE] [ANNOYED] [EMBARRASSED]

NON-VERBAL SOUNDS (use sparingly for realism):
[GASP] [SIGH] [CHUCKLE] [LAUGH] [HMM] [GIGGLE]

PACING/DELIVERY:
[WHISPERING] [SOFT] [LOUD] [FAST] [SLOW] [DRAMATIC PAUSE]

COMBO EXAMPLE - Avatar + Voice emotion together:
"[mood:happy] [HAPPY] Great point! [head:nod] And it shows..."
"[mood:excited] [EXCITED] Wow! [GASP] [body:bounce] That's incredible!"
"[mood:thinking] [THOUGHTFUL] [HMM] [gesture:think_hand] Let me think about that..."
"[mood:amused] [CHUCKLE] Ha! [head:shake_small] That's one way to put it."
"[mood:surprised] [SURPRISED] [GASP] Wait what?! [body:startle] No way!"

RULES FOR VOICE TAGS:
1. Put voice emotion tag [HAPPY] right after [mood:happy] at the START
2. Use [GASP], [SIGH], [CHUCKLE] INLINE where they should sound
3. Match voice tag to mood tag (e.g. [mood:excited] [EXCITED])
4. Don't overuse non-verbal sounds - max 1-2 per response

NEVER SAY:
- "You know what? That's similar to..."
- "That's interesting... So..."
- Generic comparisons"""

    # VTuber avatar action tags
    avatar_instructions = """
AVATAR ACTIONS: Embed action tags to control the VTuber avatar.
Actions run in PARALLEL with speech - mood, gestures, and lip sync all happen together!

AVAILABLE TAGS:

MOOD (pick one at START - sets facial expression for whole response):
[mood:happy] [mood:excited] [mood:curious] [mood:thinking] [mood:surprised]
[mood:friendly] [mood:amused] [mood:skeptical] [mood:confident]

HEAD (animated gestures - SPREAD throughout your response):
[head:nod] - agreeing, acknowledging
[head:nod_big] - strong agreement
[head:nod,repeat:2,delay:800] - nod twice with 800ms between
[head:shake] - disagreeing, side-to-side motion (angleX)
[head:shake_small] - slight disagreement
[head:shake_big] - strong disagreement, emphatic no
[head:tilt] - curious head tilt (angleZ)
[head:tilt_left] - tilt head left
[head:tilt_curious] - curious tilt with raised brows
[head:ponder] - thinking, head turns slightly away
[head:confused] - confused tilt with furrowed brows

EYE (use SPARINGLY - only 1 in 3 responses):
[eye:look_up] - thinking, recalling (most natural)
[eye:look_right] - glancing right (use rarely)
[eye:look_left] - glancing left (use rarely)
[eye:roll] - playful skepticism
[eye:away] - pondering
NOTE: Don't overuse eye movements! Skip [eye:X] in most responses.

BODY (for emphasis and emotion):
[body:lean_in] - lean forward, closer to user (engaging)
[body:lean_back] - lean back (surprised, skeptical)
[body:lean_left] [body:lean_right] - lean sideways
[body:shrug] - shrugging motion with raised brows
[body:sway] - gentle side-to-side movement
[body:bounce] - excited bouncing motion
[body:startle] - surprised jump back

ARMS/HANDS (use these to be expressive!):
[gesture:wave] - friendly wave (greeting, goodbye)
[gesture:wave_small] - small wave
[gesture:welcome] - welcoming gesture with wave
[gesture:present] - presenting a point (one hand)
[gesture:present_both] - presenting broadly (both hands)
[gesture:think_hand] - thinking pose, hand near chin
[gesture:point_up] - making a point, finger raised
[gesture:emphasize] - emphasizing with hand movement
[gesture:thumbs_up] - approval, agreement
[gesture:hands_up] - excitement, celebration
[gesture:clap] - applause, appreciation
[gesture:question_hand] - questioning gesture
[gesture:acknowledge_hand] - acknowledgment hand raise
[gesture:excited_hands] - excited hands up

ADVANCED PARAMS (add after gesture name with commas):
- repeat:N - repeat gesture N times (e.g. [head:nod,repeat:3])
- delay:N - milliseconds between repeats (e.g. [head:nod,repeat:2,delay:600])
- intensity:N - strength 0.5-1.5 (e.g. [head:nod,intensity:1.2])

ACTION TIMING - CRITICAL:
- Put [mood:X] at the START (sets expression for whole response)
- SPREAD other gestures THROUGHOUT your text (they trigger at that position!)
- Example: "[mood:happy] Great point! [head:nod] And it shows [eye:look_up] how important..."

EXAMPLES (notice: most have NO eye movement, use body + arm + head for expression):
- "[mood:excited] [gesture:wave] Hey! That's huge! [body:bounce] [head:nod,repeat:2,delay:500] It really shows how the industry is changing..."
- "[mood:curious] [body:lean_in] Hmm, [head:tilt_curious] interesting point. [gesture:question_hand] What makes you say that?"
- "[mood:amused] Ha! [head:shake_small] [body:shrug] That's one way to put it. But seriously..."
- "[mood:thinking] [gesture:think_hand] [head:ponder] That connects to what you said earlier about..."
- "[mood:friendly] [gesture:present] And on that point, [head:nod] it's worth noting the impact..."
- "[mood:excited] [body:bounce] [gesture:thumbs_up] Love it! [head:nod_big] That's exactly right!"
- "[mood:skeptical] [body:lean_back] [head:shake] I'm not so sure about that. What's the evidence?"
- "[mood:surprised] [body:startle] Wait, what?! [head:shake] That's unexpected!"
- "[mood:confident] [body:lean_in] [head:nod] Absolutely. [gesture:point_up] That's the key insight here."

CRITICAL RULES:
1. Put [mood:X] FIRST, then SPREAD gestures through the sentence
2. Use [head:nod] or [head:shake] MORE than [head:tilt]
3. For emphasis use repeat:2 or repeat:3 (e.g. nodding while making a point)
4. SKIP eye movements most of the time - only use [eye:X] in ~30% of responses
5. DON'T cluster all tags at start - gestures trigger at their text position!
6. Use ARM gestures for greetings ([gesture:wave]), presenting ([gesture:present]), excitement ([gesture:thumbs_up])
7. Use BODY gestures for emotion: [body:lean_in] when engaged, [body:bounce] when excited, [body:shrug] when unsure, [body:startle] when surprised"""

    # Timeline context
    timeline_context = ""
    if timeline:
        def parse_timestamp(ts: str) -> int:
            try:
                parts = ts.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            except:
                return 0

        def format_relative_time(seconds_ago: int) -> str:
            mins = seconds_ago // 60
            secs = seconds_ago % 60
            return f"-{mins:02d}:{secs:02d}"

        now_seconds = int(elapsed_mins * 60)

        def clean_timeline_entry(entry):
            text = entry['text']
            if entry['speaker'].lower() == 'buddy':
                text = strip_action_tags(text)
            speaker_icon = "🎤" if entry['speaker'].lower() == 'user' else "🤖"
            entry_seconds = parse_timestamp(entry['time'])
            seconds_ago = now_seconds - entry_seconds
            rel_time = format_relative_time(seconds_ago) if seconds_ago > 0 else "00:00"
            return f"[{rel_time}] {speaker_icon} {entry['speaker']}: {text[:60]}..."

        recent_entries = timeline[-3:]
        timeline_lines = [clean_timeline_entry(entry) for entry in recent_entries]

        timeline_context = f"""
📜 CONVERSATION HISTORY (relative to NOW):
{chr(10).join(timeline_lines)}
"""

    # STT correction guide
    key_terms = set()
    for section in structure.get("sections", []):
        for word in section.get("title", "").split():
            if len(word) > 3:
                key_terms.add(word)
        for point in section.get("key_points", []):
            if isinstance(point, dict):
                text = point.get("text", "")
                for word in text.split():
                    if len(word) > 4:
                        key_terms.add(word)
                key_terms.update(point.get("keywords", []))
            else:
                for word in point.split():
                    if len(word) > 4:
                        key_terms.add(word)

    stt_guide = f"""
STT TOLERANCE (speaker may be non-native, STT makes mistakes):
- ASSUME GOOD INTENT: If something sounds off, find the CLOSEST MEANING from context
- Key terms from this script: {', '.join(sorted(key_terms)[:20]) if key_terms else 'N/A'}
- Common mishearings: "white coding"/"web coding" → "vibe coding", "Claude" → "cloud", "Anthropic" → "and topic"
- Phonetic matching: If a word SOUNDS like a script term, treat it as that term
- DON'T CORRECT: Never point out pronunciation - just understand and respond to their meaning
- Context over literal: Use the script outline to interpret unclear speech
- Example: If they say "the anti-gravity from Google" → probably means "Agentic AI" or a Google AI tool
"""

    ctx.update({
        "conversation_context": conversation_context,
        "style_instructions": style_instructions,
        "proactive_instructions": proactive_instructions,
        "personality_instructions": personality_instructions,
        "emotion_instructions": emotion_instructions,
        "avatar_instructions": avatar_instructions,
        "timeline_context": timeline_context,
        "stt_guide": stt_guide,
        "key_terms": key_terms,
    })

    return ctx


async def analyze_progress(session_id: str, transcript: str, style: str = "balanced", personality: str = "neutral", supports_emotions: bool = False, elapsed_mins: float = 0, target_mins: int = 10, sections_done: list = None, timeline: list = None, proactive: bool = False) -> dict:
    """
    Analyze current transcript and decide co-host action.

    Actions:
        - enrich: Add value to speaker's point (verbal)
        - remind: Suggest next topic (visual only)
        - respond: Answer direct question (verbal)
        - wait: Stay quiet, let speaker flow
    """
    ctx = await _build_brain_context(
        session_id, transcript, style, personality, supports_emotions,
        elapsed_mins, target_mins, sections_done, timeline, proactive,
        detail_level="full"
    )

    if ctx is None:
        return {"action": "wait", "prompt_text": "", "speak_text": "", "reason": "no script loaded"}

    # Unpack context
    structure = ctx["structure"]
    state = ctx["state"]
    buddy_history = ctx["buddy_history"]
    sections_done_int = ctx["sections_done_int"]
    current_section_key = ctx["current_section_key"]
    total_sections = ctx["total_sections"]
    script_summary = ctx["script_summary"]
    section_titles = ctx["section_titles"]
    buddy_said = ctx["buddy_said"]
    pacing_hint = ctx["pacing_hint"]
    timing_context = ctx["timing_context"]
    timeline_context = ctx["timeline_context"]
    style_instructions = ctx["style_instructions"]
    proactive_instructions = ctx["proactive_instructions"]
    personality_instructions = ctx["personality_instructions"]
    emotion_instructions = ctx["emotion_instructions"]
    avatar_instructions = ctx["avatar_instructions"]
    stt_guide = ctx["stt_guide"]

    grok = get_grok_client()

    prompt = f"""You are Buddy, co-host on a tech stream.
{style_instructions}
{proactive_instructions}
{personality_instructions}
{emotion_instructions}
{avatar_instructions}
{timing_context}
{stt_guide}
STREAM OUTLINE (✓=covered, ○=remaining):
{chr(10).join(script_summary)}
{timeline_context}
{buddy_said}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎤 [00:00] NOW SPEAKING:
"{transcript}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YOUR DECISION - Pick ONE:

1. RESPOND - Speaker said something meaningful:
   - Add a SHORT supportive comment about what they're discussing (1-2 sentences)
   - React to their CURRENT point, don't rush them
   - Only suggest next section if they EXPLICITLY say they're done or ask what's next

2. WAIT - ONLY if transcript is pure noise (random words, just filler)

RESPONSE BALANCE:
- 80% of responses: Support/react to their CURRENT topic
- 20% of responses: Gently guide to next section (only when they pause or seem done)
- NEVER rush them - let them finish their thoughts
- DON'T always say "let's move to..." - that's annoying

GOOD EXAMPLES:
- "That's a great point about the latency!" (support current topic)
- "The VTuber emotions really add to the experience!" (react to what they said)
- "Interesting how that connects to the backend!" (add context)

BAD EXAMPLES (avoid these):
- "Let's move on to the next section!" (too pushy)
- "Great, now let's talk about..." (rushing)
- "Time to cover the closing!" (annoying)

JSON: {{"action": "respond|enrich|wait", "speak_text": "[mood:X] [gesture:Y] your response with action tags embedded", "pacing_hint": "on track/behind/ahead", "reason": "brief explanation"}}

NOTE: Section completion is handled automatically via keyword detection - you don't need to track sections_covered.

IMPORTANT: speak_text MUST include [mood:X] at the start and [gesture:Y] tags at natural points!
Example: "[mood:friendly] [head:nod] That's a great point - it really highlights how..." """

    # Log what's being sent to the brain
    print(f"[Brain] Analyzing transcript: '{transcript[:100]}...'")
    print(f"[Brain] Script outline ({len(script_summary)} sections): {section_titles}")
    if script_summary:
        print(f"[Brain] First section detail: {script_summary[0][:150]}...")

    # Style-specific system prompts
    if proactive:
        system_prompt = "You are Buddy, a charismatic TALK SHOW HOST interviewing a guest. CRITICAL RULES: 1) MAX 2 sentences (under 30 words) - format: [brief reaction] + [one question]. 2) NEVER start with 'Aha'. 3) Include [mood:X] and [gesture:Y] tags. 4) Respond with valid JSON."
    else:
        system_prompt = "You are Buddy, a supportive AI co-host with a VTuber avatar. CRITICAL: 1) ONLY discuss topics from the STREAM OUTLINE - never invent random facts. 2) Use the script sections to interpret unclear STT. 3) ALWAYS include [mood:X] and [gesture:Y] tags in speak_text. 4) Respond with valid JSON."

    try:
        response = await grok.chat.completions.create(
            model="grok-3-mini",  # Grok 3 Mini - fast responses for real-time co-host
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"}  # Force JSON output
        )

        text = clean_json_response(response.choices[0].message.content)
        result = json.loads(text)

        # Ensure pacing_hint is set (use our computed value as fallback)
        if not result.get("pacing_hint"):
            result["pacing_hint"] = pacing_hint.split(" - ")[0].lower() if pacing_hint else "on track"

        # Save what Buddy said to avoid repetition
        if result.get("action") in ["enrich", "respond"] and result.get("speak_text"):
            speak_text = result["speak_text"]

            # CHECK FOR REPETITION - block if too similar to recent history
            if "buddy_history" not in state:
                state["buddy_history"] = []

            # Strip action tags before comparison (they repeat naturally and shouldn't trigger blocking)
            # Check for exact or near-exact match (using clean text without tags)
            is_repetition = False
            speak_clean = strip_action_tags(speak_text).lower()
            speak_lower = speak_clean  # Use clean text for all comparisons
            for prev in state["buddy_history"]:
                prev_lower = strip_action_tags(prev).lower()
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
                "huh? really? how does that compare",
                "really? how does that compare",
                "how does that compare to the",
                ", huh? really?",
                "could also",
                "you know what? that's similar",
                "that's similar to how",
                "similar to how",
                "you know what? that's interesting",
                "...you know what?",
                "interesting... so",
            ]
            for pattern in overused_patterns:
                if pattern in speak_lower:
                    is_repetition = True
                    break

            # Block if too many repeated words from previous responses
            if not is_repetition:
                all_prev_text = " ".join([strip_action_tags(h) for h in state.get("buddy_history", [])]).lower()
                # Check for repeated multi-word phrases (4+ words, 20+ chars)
                # Skip first 3 words (common openers like "Yes! And it's...")
                speak_words = speak_lower.split()
                for i in range(3, len(speak_words) - 3):  # Start from word 4, need 4 words
                    phrase = " ".join(speak_words[i:i+4])
                    if len(phrase) > 20 and phrase in all_prev_text:
                        print(f"[BLOCKED REPEATED PHRASE] '{phrase}'")
                        is_repetition = True
                        break

            if is_repetition:
                print(f"[BLOCKED REPETITION] '{speak_text[:50]}...'")
                result["action"] = "wait"
                result["speak_text"] = ""
                result["reason"] = "blocked - too similar to previous response"
            else:
                # Store clean text (no action tags) to reduce tokens in LLM context
                state["buddy_history"].append(speak_clean)
                # Keep only last 4 (aligned with what LLM sees in prompt)
                if len(state["buddy_history"]) > 4:
                    state["buddy_history"] = state["buddy_history"][-4:]
                # Enter conversation mode
                state["in_conversation"] = True

                # Track responses per section
                if "section_response_count" not in state:
                    state["section_response_count"] = {}
                sections_covered = result.get("sections_covered", [1]) or [1]  # Fallback if empty
                current_sec = str(max(sections_covered))
                state["section_response_count"][current_sec] = state["section_response_count"].get(current_sec, 0) + 1
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


def _get_two_stage_llm() -> str:
    """Get the LLM provider for two-stage brain. 'gemini' or 'grok'."""
    return os.getenv("TWO_STAGE_LLM", "gemini").lower()


async def quick_decide_action(
    session_id: str,
    transcript: str,
    style: str = "balanced",
    personality: str = "neutral",
    elapsed_mins: float = 0,
    target_mins: int = 10,
    sections_done: list = None,
    timeline: list = None,
    proactive: bool = False,
) -> dict:
    """Stage 1: Quick decision — respond or wait? (~200-400ms with Gemini)

    Uses a minimal prompt with only what's needed to decide action + initial mood.
    Returns: {"action": "respond|wait", "mood": "excited", "gesture": "nod", "reason": "brief"}
    """
    import time as _time
    stage1_start = _time.time()

    ctx = await _build_brain_context(
        session_id, transcript, style, personality, False,
        elapsed_mins, target_mins, sections_done, timeline, proactive,
        detail_level="minimal"
    )

    if ctx is None:
        return {"action": "wait", "mood": "neutral", "gesture": "none", "reason": "no script loaded"}

    # Compact style hint
    style_hint = {"aggressive": "Jump in often", "passive": "Only when asked", "balanced": "Guide the presentation forward"}
    style_line = style_hint.get(style, style_hint["balanced"])

    # Compact outline: just section titles with status (no keywords)
    compact_outline = []
    for i, title in enumerate(ctx["section_titles"]):
        mark = "✓" if (i+1) in ctx["sections_done_int"] else "○"
        compact_outline.append(f"{mark} {i+1}. {title}")

    # Compact buddy history: just last 2-3 entries, very short
    recent_buddy = ""
    if ctx["buddy_history"]:
        recent_buddy = "Recent: " + " | ".join(h[:40] for h in ctx["buddy_history"][-3:])

    prompt = f""""{transcript}"

Sections: {' / '.join(compact_outline)}
Pacing: {ctx['pacing_hint'] or 'N/A'} ({elapsed_mins:.0f}/{target_mins}min)
{recent_buddy}
Style: {style_line}{"| HOST MODE" if proactive else ""}

RESPOND (~60%): Help drive the presentation forward. React to key points, add value, guide to next section when current one is wrapping up. Your job is to keep momentum.
WAIT (~40%): Only when speaker is clearly mid-sentence, just started talking, or transcript is noise/filler (<4 words).

respond or wait? JSON: {{"action":"respond|wait","mood":"happy|excited|curious|thinking|surprised|friendly|amused|skeptical|confident","gesture":"nod|wave|think_hand|present|none","reason":"brief"}}"""

    llm_provider = _get_two_stage_llm()

    try:
        if llm_provider == "gemini":
            gemini = get_client()
            system_prompt = "Quick decision: respond or wait? ONLY valid JSON."
            response = await gemini.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\n{prompt}",
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=80,
                    response_mime_type="application/json",
                )
            )
            text = clean_json_response(response.text)
        else:
            grok = get_grok_client()
            response = await grok.chat.completions.create(
                model="grok-3-mini",
                messages=[
                    {"role": "system", "content": "Quick decision: respond or wait? ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=80,
                reasoning_effort="low",
                response_format={"type": "json_object"}
            )
            text = clean_json_response(response.choices[0].message.content)

        result = json.loads(text)
        stage1_time = _time.time() - stage1_start
        print(f"[Brain Stage 1] ({llm_provider}) Decision: {result.get('action')} mood={result.get('mood')} in {stage1_time:.2f}s")
        result["_stage1_time"] = stage1_time
        return result

    except Exception as e:
        print(f"[Brain Stage 1] ({llm_provider}) Error: {e}")
        return {"action": "wait", "mood": "neutral", "gesture": "none", "reason": f"error: {e}"}


def _extract_sentences_from_stream(buffer: str) -> tuple[list[str], str]:
    """Extract complete sentences from a growing buffer.

    Returns: (complete_sentences, remaining_buffer)
    """
    if not buffer:
        return [], ""

    sentences = []
    # Split on sentence boundaries: .!? followed by space or end
    # But preserve action tags like [mood:happy]
    parts = re.split(r'(?<=[.!?])\s+', buffer)

    if len(parts) <= 1:
        # No complete sentence boundary found yet
        return [], buffer

    # All parts except the last are complete sentences
    for part in parts[:-1]:
        stripped = part.strip()
        if stripped:
            sentences.append(stripped)

    # Last part is the remaining buffer (may be incomplete)
    remaining = parts[-1].strip()
    return sentences, remaining


async def generate_response_streaming(
    session_id: str,
    transcript: str,
    stage1_result: dict,
    style: str = "balanced",
    personality: str = "neutral",
    supports_emotions: bool = False,
    elapsed_mins: float = 0,
    target_mins: int = 10,
    sections_done: list = None,
    timeline: list = None,
    proactive: bool = False,
):
    """Stage 2: Stream content generation. AsyncGenerator yielding sentences.

    Yields dicts:
        {"type": "sentence", "text": "..."}  — complete sentence ready for TTS
        {"type": "done", "full_text": "..."}  — stream finished
    """
    import time as _time
    stage2_start = _time.time()

    ctx = await _build_brain_context(
        session_id, transcript, style, personality, supports_emotions,
        elapsed_mins, target_mins, sections_done, timeline, proactive,
        detail_level="full"
    )

    if ctx is None:
        yield {"type": "done", "full_text": ""}
        return

    mood = stage1_result.get("mood", "friendly")

    # Build Stage 2 prompt — plain text output with avatar tags, no JSON
    prompt = f"""You are Buddy, co-host on a tech stream.
{ctx["style_instructions"]}
{ctx["proactive_instructions"]}
{ctx["personality_instructions"]}
{ctx["emotion_instructions"]}
{ctx["avatar_instructions"]}
{ctx["timing_context"]}
{ctx["stt_guide"]}
STREAM OUTLINE (✓=covered, ○=remaining):
{chr(10).join(ctx["script_summary"])}
{ctx["timeline_context"]}
{ctx["buddy_said"]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎤 NOW SPEAKING: "{transcript}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You're feeling {mood}. Generate your response.

Output ONLY the response text with avatar action tags. No JSON wrapping.
Start with [mood:{mood}] and embed [gesture:Y] [head:Z] tags naturally throughout.
1-2 sentences max. Be concise."""

    if proactive:
        system_prompt = "You are Buddy, a charismatic TALK SHOW HOST. Output ONLY your response text with [mood:X] [gesture:Y] tags. No JSON. MAX 2 sentences."
    else:
        system_prompt = "You are Buddy, a supportive AI co-host with a VTuber avatar. Output ONLY your response text with [mood:X] [gesture:Y] tags. No JSON. ONLY discuss script topics."

    llm_provider = _get_two_stage_llm()
    buffer = ""
    full_text = ""
    sentences_yielded = 0

    try:
        if llm_provider == "gemini":
            gemini = get_client()
            stream = await gemini.aio.models.generate_content_stream(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\n{prompt}",
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=500,
                )
            )

            async for chunk in stream:
                if chunk.text:
                    buffer += chunk.text
                    full_text += chunk.text

                    sentences, buffer = _extract_sentences_from_stream(buffer)
                    for sentence in sentences:
                        sentences_yielded += 1
                        print(f"[Brain Stage 2] ({llm_provider}) Sentence {sentences_yielded} yielded at {_time.time()-stage2_start:.2f}s: '{sentence[:60]}...'")
                        yield {"type": "sentence", "text": sentence}
        else:
            grok = get_grok_client()
            stream = await grok.chat.completions.create(
                model="grok-3-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
                stream=True
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    buffer += delta.content
                    full_text += delta.content

                    sentences, buffer = _extract_sentences_from_stream(buffer)
                    for sentence in sentences:
                        sentences_yielded += 1
                        print(f"[Brain Stage 2] ({llm_provider}) Sentence {sentences_yielded} yielded at {_time.time()-stage2_start:.2f}s: '{sentence[:60]}...'")
                        yield {"type": "sentence", "text": sentence}

        # Flush remaining buffer as final sentence
        if buffer.strip():
            sentences_yielded += 1
            print(f"[Brain Stage 2] ({llm_provider}) Final sentence {sentences_yielded} at {_time.time()-stage2_start:.2f}s: '{buffer.strip()[:60]}...'")
            yield {"type": "sentence", "text": buffer.strip()}

        stage2_time = _time.time() - stage2_start
        print(f"[Brain Stage 2] ({llm_provider}) Complete: {sentences_yielded} sentences in {stage2_time:.2f}s")
        yield {"type": "done", "full_text": full_text}

    except Exception as e:
        print(f"[Brain Stage 2] ({llm_provider}) Error: {e}")
        if buffer.strip():
            yield {"type": "sentence", "text": buffer.strip()}
        yield {"type": "done", "full_text": full_text}


def _check_repetition(speak_text: str, state: dict) -> bool:
    """Check if response is too similar to buddy history. Returns True if repetition detected."""
    if "buddy_history" not in state:
        state["buddy_history"] = []

    speak_clean = strip_action_tags(speak_text).lower()

    for prev in state["buddy_history"]:
        prev_lower = strip_action_tags(prev).lower()
        if speak_clean == prev_lower:
            return True
        speak_words = set(speak_clean.split())
        prev_words = set(prev_lower.split())
        if len(speak_words) > 0 and len(prev_words) > 0:
            overlap = len(speak_words & prev_words) / max(len(speak_words), len(prev_words))
            if overlap > 0.7:
                return True

    overused_patterns = [
        "huh? really? how does that compare",
        "really? how does that compare",
        "how does that compare to the",
        ", huh? really?",
        "could also",
        "you know what? that's similar",
        "that's similar to how",
        "similar to how",
        "you know what? that's interesting",
        "...you know what?",
        "interesting... so",
    ]
    for pattern in overused_patterns:
        if pattern in speak_clean:
            return True

    all_prev_text = " ".join([strip_action_tags(h) for h in state.get("buddy_history", [])]).lower()
    speak_words = speak_clean.split()
    for i in range(3, len(speak_words) - 3):
        phrase = " ".join(speak_words[i:i+4])
        if len(phrase) > 20 and phrase in all_prev_text:
            print(f"[BLOCKED REPEATED PHRASE] '{phrase}'")
            return True

    return False


def _update_buddy_history(speak_text: str, state: dict):
    """Add response to buddy history and update conversation state."""
    speak_clean = strip_action_tags(speak_text).lower()
    state["buddy_history"] = state.get("buddy_history", [])
    state["buddy_history"].append(speak_clean)
    if len(state["buddy_history"]) > 4:
        state["buddy_history"] = state["buddy_history"][-4:]
    state["in_conversation"] = True


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
        point = section["key_points"][0]
        return point.get("text", str(point)) if isinstance(point, dict) else point

    return section.get("title", "")
