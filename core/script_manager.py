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
            "key_points": [
                {{
                    "text": "point description",
                    "type": "speech|action",
                    "keywords": ["keyword1", "keyword2"],
                    "action_trigger": "gesture:wave" (only if type is action)
                }}
            ],
            "suggested_phrases": ["how to start this section"],
            "duration_secs": number (seconds for this section)
        }}
    ],
    "total_sections": number
}}

KEY POINT TYPES:
- "speech": Something the speaker would SAY. Extract 2-4 important keywords from the text.
  Example: {{"text": "Introduce yourself", "type": "speech", "keywords": ["introduce", "yourself", "name"]}}
- "action": Something the AI avatar should DO. Include action_trigger.
  Example: {{"text": "Trigger wave greeting", "type": "action", "keywords": ["wave", "greeting"], "action_trigger": "gesture:wave"}}

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
            model="gemini-3-flash-preview",  # or "gemini-2.0-flash-exp" for cheaper
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=4000
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


async def analyze_progress(session_id: str, transcript: str, style: str = "balanced", personality: str = "neutral", supports_emotions: bool = False, elapsed_mins: float = 0, target_mins: int = 10, sections_done: list = None, timeline: list = None) -> dict:
    """
    Analyze current transcript and decide co-host action.

    Actions:
        - enrich: Add value to speaker's point (verbal)
        - remind: Suggest next topic (visual only)
        - respond: Answer direct question (verbal)
        - wait: Stay quiet, let speaker flow
    """
    if sections_done is None:
        sections_done = []
    if timeline is None:
        timeline = []

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

    # Track responses per section for transition logic
    section_response_count = state.get("section_response_count", {})
    current_section_key = str(max(sections_done)) if sections_done else "0"

    grok = get_grok_client()

    # Build script summary with section IDs for tracking
    section_titles = []
    script_summary = []
    total_sections = len(structure.get("sections", []))
    print(f"[Brain] Script title: {structure.get('title', 'NO TITLE')}, sections: {total_sections}")
    for i, s in enumerate(structure.get("sections", [])):
        section_titles.append(s['title'])
        points = s.get("key_points", [])[:4]  # Show more points for matching
        covered_mark = "✓" if (i+1) in sections_done else "○"
        # Add keywords to help matching - handle both dict and string format
        keywords_list = []
        for p in points:
            if isinstance(p, dict):
                keywords_list.extend(p.get("keywords", []))
            else:
                keywords_list.append(p)
        keywords = ", ".join(keywords_list) if keywords_list else s['title']
        script_summary.append(f"[{i+1}] {covered_mark} {s['title']}\n    Keywords: {keywords}")
        if i == 0:  # Log first section as sample
            print(f"[Brain] First section: {s['title']}, points: {points[:2]}")

    # Build buddy history string - make it prominent
    buddy_said = ""
    if buddy_history:
        buddy_said = f"""

⚠️ YOUR PREVIOUS RESPONSES (DO NOT REPEAT):
{chr(10).join(f'- "{h[:100]}..."' for h in buddy_history)}

CRITICAL: Say something DIFFERENT each time. Don't repeat the same facts or phrases."""

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
STYLE: BALANCED - Engage consistently! Default is to RESPOND, not wait.

YOU SHOULD RESPOND (this is your default):
- If transcript has 5+ words of real content → RESPOND
- If speaker mentions any topic from the script → RESPOND
- If speaker seems to be making a point → RESPOND
- If it's been a while since you spoke → RESPOND

ONLY WAIT if:
- Transcript is CLEARLY just noise/errors (random words that make no sense)
- Transcript is ONLY filler words ("um", "so", "okay", "uh")
- Less than 4 words total

IMPORTANT: When in doubt, RESPOND with something supportive. It's better to engage than stay silent."""

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

    # VTuber avatar action tags - ALWAYS include these
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

    # Build conversation timeline with RELATIVE timestamps (NOW = 00:00, past = negative)
    timeline_context = ""
    if timeline:
        def parse_timestamp(ts: str) -> int:
            """Parse MM:SS to total seconds"""
            try:
                parts = ts.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            except:
                return 0

        def format_relative_time(seconds_ago: int) -> str:
            """Format as -MM:SS for past events"""
            mins = seconds_ago // 60
            secs = seconds_ago % 60
            return f"-{mins:02d}:{secs:02d}"

        # Get current time from elapsed_mins
        now_seconds = int(elapsed_mins * 60)

        def clean_timeline_entry(entry):
            text = entry['text']
            if entry['speaker'].lower() == 'buddy':
                text = strip_action_tags(text)
            speaker_icon = "🎤" if entry['speaker'].lower() == 'user' else "🤖"

            # Calculate relative time (how long ago)
            entry_seconds = parse_timestamp(entry['time'])
            seconds_ago = now_seconds - entry_seconds
            rel_time = format_relative_time(seconds_ago) if seconds_ago > 0 else "00:00"

            return f"[{rel_time}] {speaker_icon} {entry['speaker']}: {text[:60]}..."

        # Show last 3 entries (limited to prevent LLM confusion in later sections)
        recent_entries = timeline[-3:]
        timeline_lines = [clean_timeline_entry(entry) for entry in recent_entries]

        timeline_context = f"""
📜 CONVERSATION HISTORY (relative to NOW):
{chr(10).join(timeline_lines)}
"""

    # Build timing and coverage context
    sections_remaining = [i+1 for i in range(total_sections) if (i+1) not in sections_done]
    time_remaining = max(0, target_mins - elapsed_mins)
    coverage_pct = (len(sections_done) / total_sections * 100) if total_sections > 0 else 0
    time_pct = (elapsed_mins / target_mins * 100) if target_mins > 0 else 0

    # Calculate expected section based on time
    expected_section = min(int((time_pct / 100) * total_sections) + 1, total_sections) if total_sections > 0 else 1
    current_max_section = max(sections_done) if sections_done else 0

    # Determine pacing hint and transition need
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

    # Get next section title for transition
    next_section_title = ""
    next_section_num = current_max_section + 1
    if next_section_num <= total_sections:
        next_section = structure.get("sections", [])[next_section_num - 1] if next_section_num <= len(structure.get("sections", [])) else None
        if next_section:
            next_section_title = next_section.get("title", "")

    # Get response count for current section
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

    # Extract key terms from script for STT correction guidance
    key_terms = set()
    for section in structure.get("sections", []):
        # Add section title words
        for word in section.get("title", "").split():
            if len(word) > 3:
                key_terms.add(word)
        # Add key points words - handle both dict and string format
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

    # Build STT correction guide with tolerance for non-native speakers
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

    prompt = f"""You are Buddy, co-host on a tech stream.
{style_instructions}
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

JSON: {{"action": "respond|enrich|wait", "speak_text": "[mood:X] [gesture:Y] your response with action tags embedded", "sections_covered": [all section numbers touched], "pacing_hint": "on track/behind/ahead", "reason": "brief explanation"}}

IMPORTANT: speak_text MUST include [mood:X] at the start and [gesture:Y] tags at natural points!
Example: "[mood:friendly] [head:nod] That's a great point - it really highlights how..." """

    # Log what's being sent to the brain
    print(f"[Brain] Analyzing transcript: '{transcript[:100]}...'")
    print(f"[Brain] Script outline ({len(script_summary)} sections): {section_titles}")
    if script_summary:
        print(f"[Brain] First section detail: {script_summary[0][:150]}...")

    try:
        response = await grok.chat.completions.create(
            model="grok-3-mini",  # Grok 3 Mini - fast responses for real-time co-host
            messages=[
                {"role": "system", "content": "You are Buddy, a supportive AI co-host with a VTuber avatar. CRITICAL: 1) ONLY discuss topics from the STREAM OUTLINE - never invent random facts. 2) Use the script sections to interpret unclear STT. 3) ALWAYS include [mood:X] and [gesture:Y] tags in speak_text. 4) Respond with valid JSON."},
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
