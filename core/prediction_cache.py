"""
Prediction Cache - Pre-generate TTS audio for predicted keyword responses.
Reduces latency from ~7s to ~50ms on cache hits.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# LLM client for prediction generation (using Grok/xAI)
_grok_client: AsyncOpenAI | None = None


def get_grok_client() -> AsyncOpenAI:
    """Get xAI Grok client for prediction generation."""
    global _grok_client
    if _grok_client is None:
        _grok_client = AsyncOpenAI(
            api_key=os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1"
        )
    return _grok_client


class PredictionCache:
    """
    Pre-generates TTS audio for predicted keyword→response pairs.

    Flow:
    1. After script loads, generate predictions via lightweight LLM call
    2. Pre-generate TTS for each prediction, store in Redis
    3. On STT result, check if transcript matches any cached keyword
    4. If hit: return cached audio instantly (skip Brain+TTS)
    5. On section complete: cleanup that section's cache entries
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.keyword_map: dict[str, dict] = {}  # keyword -> {section_id, cache_key, response}
        self.stats = {"hits": 0, "misses": 0, "generated": 0}
        self.generating = False
        self.welcome_cached = False  # Track if welcome speech is cached
        self._redis_loaded = False  # Track if we've loaded from Redis

    async def load_from_redis(self) -> int:
        """Load existing cached keywords from Redis (for reconnect scenarios)."""
        if self._redis_loaded:
            return len(self.keyword_map)

        from core.redis_client import get_redis
        try:
            r = await get_redis()
            # Find all voice cache keys for this session
            pattern = f"stream:{self.session_id}:voice_cache:*"
            keys = await r.keys(pattern)

            loaded = 0
            for key in keys:
                raw = await r.get(key)
                if not raw:
                    continue

                data = json.loads(raw)
                if data and data.get("keyword"):
                    keyword = data["keyword"].lower()
                    section_id = int(data.get("section_id", 0))
                    cache_key = self._make_cache_key(section_id, keyword)

                    self.keyword_map[keyword] = {
                        "section_id": section_id,
                        "cache_key": cache_key,
                        "response": data.get("response_text", "")
                    }
                    loaded += 1

            self._redis_loaded = True
            if loaded > 0:
                logger.info(f"[{self.session_id}] Loaded {loaded} keywords from Redis: {list(self.keyword_map.keys())}")
            return loaded

        except Exception as e:
            logger.error(f"[{self.session_id}] Failed to load from Redis: {e}")
            return 0

    async def generate_all_predictions(
        self,
        structure: dict,
        voice: str,
        tts_model: str,
        proactive_mode: bool = False,
        target_duration_mins: int = 10
    ) -> dict:
        """
        Generate predictions for all sections and pre-cache TTS audio.
        Also preloads welcome speech for instant playback on start.
        Runs as background task - doesn't block session start.

        Args:
            structure: Parsed script structure with sections
            voice: ElevenLabs voice ID
            tts_model: TTS model name
            proactive_mode: Whether proactive mode is enabled
            target_duration_mins: Target presentation duration

        Returns:
            Dict with generation stats
        """
        if self.generating:
            logger.warning(f"[{self.session_id}] Prediction generation already in progress")
            return {"error": "already_generating"}

        self.generating = True
        start_time = time.time()

        try:
            from core.redis_client import store_voice_cache
            from core.tts_client import text_to_speech

            sections = structure.get("sections", [])

            # === PRELOAD WELCOME SPEECH FIRST ===
            await self._preload_welcome_speech(structure, voice, tts_model, proactive_mode, target_duration_mins)
            if not sections:
                logger.info(f"[{self.session_id}] No sections to generate predictions for")
                return {"generated": 0}

            # Step 1: Generate predictions via LLM (lightweight call)
            predictions = await self._generate_predictions_llm(sections)

            if not predictions:
                logger.warning(f"[{self.session_id}] LLM returned no predictions")
                return {"generated": 0}

            # Step 2: Pre-generate TTS for each prediction
            generated_count = 0
            skipped_count = 0
            max_predictions = 6  # Limit total cached predictions

            # Minimal blocklist - only truly generic phrases
            generic_keywords = {
                'hi', 'hey', 'yes', 'no', 'ok', 'okay', 'hello', 'thanks', 'thank you',
                'your role', 'key takeaway', 'key takeaways', 'final thought', 'final thoughts',
                'main point', 'main points', 'any questions', 'wrap up', 'introduction', 'conclusion'
            }

            # Build section_id → title lookup from original sections
            section_title_map = {}
            for section in sections:
                section_title_map[section.get("id", 0)] = section.get("title", "")

            for section_pred in predictions:
                # Stop if we've reached the limit
                if generated_count >= max_predictions:
                    logger.info(f"[{self.session_id}] Reached max predictions ({max_predictions}), stopping")
                    break

                section_id = section_pred.get("section_id")
                section_label = section_pred.get("section_label", "Core")
                section_title = section_title_map.get(section_id, "")
                for pred in section_pred.get("predictions", []):
                    # Stop if we've reached the limit
                    if generated_count >= max_predictions:
                        break

                    keyword = pred.get("keyword", "").lower().strip()
                    response = pred.get("response", "")

                    if not keyword or not response:
                        logger.debug(f"[{self.session_id}] Skipping empty keyword/response")
                        continue

                    # Only skip exact matches to generic keywords
                    if len(keyword) < 4 or keyword in generic_keywords:
                        logger.info(f"[{self.session_id}] Skipping generic keyword '{keyword}'")
                        skipped_count += 1
                        continue

                    try:
                        # Generate TTS audio
                        # Strip action tags for TTS but keep them for avatar
                        clean_response = self._strip_action_tags(response)
                        audio_base64 = await text_to_speech(clean_response, voice, tts_model)

                        if not audio_base64:
                            continue

                        # Create cache key
                        cache_key = self._make_cache_key(section_id, keyword)

                        # Store in Redis
                        await store_voice_cache(
                            self.session_id,
                            section_id,
                            keyword,
                            response,  # Keep original response with tags
                            audio_base64
                        )

                        # Add to in-memory lookup map
                        self.keyword_map[keyword] = {
                            "section_id": section_id,
                            "cache_key": cache_key,
                            "response": response,
                            "section_label": section_label,
                            "section_title": section_title
                        }

                        generated_count += 1
                        logger.debug(f"[{self.session_id}] Cached prediction: '{keyword}' -> '{response[:30]}...'")

                    except Exception as e:
                        logger.error(f"[{self.session_id}] Failed to cache prediction '{keyword}': {e}")

            self.stats["generated"] = generated_count
            elapsed = time.time() - start_time

            # Build detailed keywords list with responses
            keywords_with_responses = []
            for keyword, entry in self.keyword_map.items():
                # Strip action tags from response for display
                clean_response = self._strip_action_tags(entry["response"])
                keywords_with_responses.append({
                    "keyword": keyword,
                    "response": clean_response[:80] + "..." if len(clean_response) > 80 else clean_response,
                    "section_id": entry["section_id"],
                    "section_label": entry.get("section_label", "Core"),
                    "section_title": entry.get("section_title", "")
                })

            logger.info(f"[{self.session_id}] Prediction cache: {generated_count} cached, {skipped_count} skipped in {elapsed:.1f}s")
            logger.info(f"[{self.session_id}] Cached keywords: {[k['keyword'] for k in keywords_with_responses]}")

            return {
                "generated": generated_count,
                "elapsed_seconds": round(elapsed, 1),
                "keywords": keywords_with_responses
            }

        except Exception as e:
            logger.error(f"[{self.session_id}] Prediction generation failed: {e}")
            return {"error": str(e)}
        finally:
            self.generating = False

    async def _generate_predictions_llm(self, sections: list) -> list:
        """
        Call LLM to generate keyword→response predictions.
        Uses a lightweight prompt with only section titles + key points.
        """
        # Build minimal context for LLM
        sections_context = []
        all_section_keywords = set()  # Collect all section keywords to exclude

        for section in sections:
            section_id = section.get("id", 0)
            title = section.get("title", "")
            keywords = section.get("section_keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",") if k.strip()]

            # Track section keywords to exclude from predictions
            for kw in keywords:
                all_section_keywords.add(kw.lower())

            # Get first 2 key points for context
            key_points = []
            for p in section.get("key_points", [])[:2]:
                if isinstance(p, dict):
                    key_points.append(p.get("text", ""))
                else:
                    key_points.append(str(p))

            sections_context.append({
                "section_id": section_id,
                "title": title,
                "keywords": keywords[:5],  # Limit to 5 keywords
                "key_points": key_points
            })

        # Store excluded keywords for filtering
        self._excluded_keywords = all_section_keywords

        # Determine total sections for position labeling
        total_sections = len(sections_context)

        prompt = f"""Generate keyword→response predictions for an AI co-host during a live stream presentation.

For EACH section, generate exactly 1 keyword trigger based on the section's MOST IMPORTANT topic.

RULES:
1. Keywords: 2-3 words, the KEY TOPIC of that section (e.g., "software testing", "bug detection")
2. AVOID generic phrases: your role, key takeaways, core concepts, real examples, final thoughts
3. Responses: 1-2 sentences with [mood:X] tag (friendly/curious/excited/thoughtful)
4. Only 1 prediction per section (total 5-6 keywords max)
5. For each prediction, include "section_label": a short label classifying the section's role in the presentation.
   Use one of: "Intro", "Core", or "Ending". The first section is typically "Intro", the last section is typically "Ending", and sections in between are "Core".

There are {total_sections} sections total.

Sections:
{json.dumps(sections_context, indent=2)}

Output JSON array with exactly 1 prediction per section:
[
  {{"section_id": 1, "section_label": "Intro", "predictions": [
    {{"keyword": "<topic from this section>", "response": "[mood:friendly] Response about that topic..."}}
  ]}},
  {{"section_id": 2, "section_label": "Core", "predictions": [
    {{"keyword": "<another topic>", "response": "[mood:curious] Another response..."}}
  ]}}
]

Only output valid JSON, no markdown."""

        try:
            client = get_grok_client()
            response = await client.chat.completions.create(
                model="grok-3-mini",  # Same model as script_manager
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            predictions = json.loads(content)
            # Log what was generated for debugging
            all_keywords = []
            for sp in predictions:
                for p in sp.get("predictions", []):
                    all_keywords.append(p.get("keyword", "?"))
            logger.info(f"[{self.session_id}] LLM generated {len(predictions)} sections, keywords: {all_keywords}")
            return predictions

        except json.JSONDecodeError as e:
            logger.error(f"[{self.session_id}] Failed to parse LLM predictions: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.session_id}] LLM prediction call failed: {e}")
            return []

    async def get_by_keyword(self, keyword: str) -> Optional[dict]:
        """
        Get cached response for exact keyword (for keyboard trigger).
        No fuzzy matching - direct lookup by keyword.

        Args:
            keyword: The exact keyword to look up

        Returns:
            Dict with audio_base64, response_text if found, else None
        """
        from core.redis_client import get_voice_cache

        keyword_lower = keyword.lower()
        entry = self.keyword_map.get(keyword_lower)

        if entry:
            cache_data = await get_voice_cache(self.session_id, entry["cache_key"])
            if cache_data and cache_data.get("audio_base64"):
                return {
                    "keyword": keyword,
                    "response_text": cache_data.get("response_text", entry["response"]),
                    "audio_base64": cache_data["audio_base64"],
                    "section_id": entry["section_id"]
                }
        return None

    async def lookup_keyword(self, transcript: str) -> Optional[dict]:
        """
        Check if transcript matches any cached keyword.
        Returns cached audio if hit, None if miss.

        Args:
            transcript: STT transcript (already corrected)

        Returns:
            Dict with audio_base64, response_text if hit, else None
        """
        # Try to load from Redis if map is empty (reconnect scenario)
        if not self.keyword_map:
            await self.load_from_redis()

        if not self.keyword_map:
            logger.info(f"[{self.session_id}] Cache lookup: no keywords in map (even after Redis load)")
            return None

        logger.info(f"[{self.session_id}] Cache lookup: '{transcript[:40]}' vs {list(self.keyword_map.keys())}")
        transcript_lower = transcript.lower().strip()

        # Normalize: expand contractions
        contractions = {
            "i'm": "i am", "you're": "you are", "we're": "we are", "they're": "they are",
            "it's": "it is", "that's": "that is", "what's": "what is", "how's": "how is",
            "let's": "let us", "can't": "cannot", "don't": "do not", "won't": "will not",
            "isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not"
        }
        for contraction, expansion in contractions.items():
            transcript_lower = transcript_lower.replace(contraction, expansion)

        # Strip punctuation from words
        import re
        transcript_words = set()
        for w in transcript_lower.split():
            clean_w = re.sub(r'[^\w]', '', w)  # Remove punctuation
            if clean_w:
                transcript_words.add(clean_w)

        # Also create stemmed versions (remove trailing 's' for plural matching)
        transcript_words_stemmed = set()
        for w in transcript_words:
            transcript_words_stemmed.add(w)
            if w.endswith('s') and len(w) > 3:
                transcript_words_stemmed.add(w[:-1])  # "concepts" -> "concept"
            if not w.endswith('s'):
                transcript_words_stemmed.add(w + 's')  # "concept" -> "concepts"

        # Check for keyword match - flexible matching
        best_match = None
        best_score = 0

        for keyword, entry in self.keyword_map.items():
            keyword_words = keyword.split()
            keyword_words_set = set(keyword_words)

            # Also stem keyword words for matching
            keyword_words_stemmed = set()
            for w in keyword_words:
                keyword_words_stemmed.add(w)
                if w.endswith('s') and len(w) > 3:
                    keyword_words_stemmed.add(w[:-1])
                if not w.endswith('s'):
                    keyword_words_stemmed.add(w + 's')

            # Method 1: Exact phrase match (highest priority)
            if keyword in transcript_lower:
                match_ratio = 1.0
                logger.debug(f"[{self.session_id}] Match method 1 (exact): '{keyword}'")
            # Method 2: All keyword words appear in transcript (for short keywords)
            elif len(keyword_words) <= 3 and keyword_words_set.issubset(transcript_words_stemmed):
                match_ratio = 0.95
                logger.debug(f"[{self.session_id}] Match method 2 (subset): '{keyword}' kw={keyword_words_set} in trans={transcript_words_stemmed}")
            # Method 3: Stemmed match (concept/concepts both work)
            elif len(keyword_words) <= 3 and keyword_words_stemmed & transcript_words_stemmed:
                # Check if all important keyword words match (with stemming)
                common_words = {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'tell', 'us', 'about', 'your', 'we', 'will', 'you', 'me', 'to', 'of', 'in', 'on', 'for'}
                important_kw = [w for w in keyword_words if w not in common_words and len(w) > 2]
                if not important_kw:
                    important_kw = keyword_words

                # Check match with stemming
                matched = 0
                for kw in important_kw:
                    kw_variants = {kw, kw + 's', kw[:-1] if kw.endswith('s') and len(kw) > 3 else kw}
                    if kw_variants & transcript_words_stemmed:
                        matched += 1

                if matched == len(important_kw):
                    match_ratio = 0.9
                elif matched > 0:
                    match_ratio = 0.7 * (matched / len(important_kw))
                else:
                    continue
            # Method 4: Key content words match (ignore common words)
            else:
                common_words = {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'tell', 'us', 'about', 'your', 'we', 'will', 'you', 'me', 'to', 'of', 'in', 'on', 'for'}
                important_kw_words = [w for w in keyword_words if w not in common_words and len(w) > 2]

                if not important_kw_words:
                    important_kw_words = keyword_words

                # Check how many important words match (with stemming)
                matched_important = 0
                for w in important_kw_words:
                    w_variants = {w, w + 's', w[:-1] if w.endswith('s') and len(w) > 3 else w}
                    if w_variants & transcript_words_stemmed:
                        matched_important += 1

                if matched_important == 0:
                    continue

                match_ratio = matched_important / len(important_kw_words)

                if match_ratio < 0.5:
                    continue

                match_ratio *= 0.85

            # Track best match
            if match_ratio > best_score:
                best_score = match_ratio
                best_match = (keyword, entry)

        # Log matching attempt for debugging
        if best_match:
            logger.debug(f"[{self.session_id}] Best match: '{best_match[0]}' score={best_score:.2f}")
        else:
            logger.debug(f"[{self.session_id}] No match for: '{transcript[:50]}' (words: {list(transcript_words)[:5]})")

        if best_match and best_score >= 0.5:
            keyword, entry = best_match
            # Found a match - fetch from Redis
            from core.redis_client import get_voice_cache

            cache_data = await get_voice_cache(
                self.session_id,
                entry["cache_key"]
            )

            if cache_data and cache_data.get("audio_base64"):
                self.stats["hits"] += 1
                logger.info(f"[{self.session_id}] Cache HIT: '{keyword}' (score: {best_score:.0%}, hits: {self.stats['hits']})")
                return {
                    "keyword": keyword,
                    "response_text": cache_data.get("response_text", entry["response"]),
                    "audio_base64": cache_data["audio_base64"],
                    "section_id": entry["section_id"]
                }

        self.stats["misses"] += 1
        return None

    async def cleanup_section(self, section_id: int) -> int:
        """
        Remove cache entries for a completed section.

        Args:
            section_id: Section ID to cleanup

        Returns:
            Number of entries deleted
        """
        from core.redis_client import delete_section_cache

        # Remove from in-memory map
        keywords_to_remove = [
            kw for kw, entry in self.keyword_map.items()
            if entry["section_id"] == section_id
        ]
        for kw in keywords_to_remove:
            del self.keyword_map[kw]

        # Delete from Redis
        deleted = await delete_section_cache(self.session_id, section_id)

        logger.info(f"[{self.session_id}] Cleaned up section {section_id}: {deleted} Redis keys, {len(keywords_to_remove)} memory entries")
        return deleted

    def get_stats(self) -> dict:
        """Get cache hit/miss statistics."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0

        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "generated": self.stats["generated"],
            "hit_rate_percent": round(hit_rate, 1),
            "cached_keywords": list(self.keyword_map.keys())
        }

    def get_predictions_by_section(self) -> dict:
        """Get predictions grouped by section for UI display."""
        by_section = {}
        for keyword, entry in self.keyword_map.items():
            section_id = entry["section_id"]
            if section_id not in by_section:
                by_section[section_id] = []
            by_section[section_id].append({
                "keyword": keyword,
                "cached": True,
                "hit_count": 0  # Could track per-keyword hits if needed
            })
        return by_section

    def _make_cache_key(self, section_id: int, keyword: str) -> str:
        """Create a cache key from section ID and keyword."""
        keyword_hash = hashlib.md5(keyword.encode()).hexdigest()[:8]
        return f"{section_id}:{keyword_hash}"

    def _strip_action_tags(self, text: str) -> str:
        """Remove [mood:X] [gesture:Y] etc tags for TTS."""
        import re
        return re.sub(r'\[[\w:,]+\]', '', text).strip()

    async def _preload_welcome_speech(
        self,
        structure: dict,
        voice: str,
        tts_model: str,
        proactive_mode: bool,
        target_duration_mins: int
    ) -> bool:
        """
        Pre-generate and cache welcome speech TTS for instant playback on start.
        """
        from core.redis_client import get_redis
        from core.tts_client import text_to_speech

        try:
            total_sections = structure.get("total_sections", len(structure.get("sections", [])))
            title = structure.get("title", "your presentation")

            # Generate welcome text (same logic as websocket.py start_presentation)
            if proactive_mode:
                first_section_title = ""
                sections = structure.get("sections", [])
                if sections:
                    first_section = sections[0]
                    first_section_title = first_section.get("title", "the first topic")

                welcome_text = f"[mood:excited] [gesture:wave] Hey everyone! I'm Buddy, your host today. [head:nod] We're covering {title} with {total_sections} topics, starting with {first_section_title}. [gesture:present] So, what should we know about this?"
            else:
                welcome_text = f"Hi! I'm Buddy, your AI cohost. We have {target_duration_mins} minutes and {total_sections} sections to cover. Let's make this a great presentation! Go ahead and start whenever you're ready."

            # Strip action tags for TTS
            clean_welcome = self._strip_action_tags(welcome_text)

            # Generate TTS audio
            logger.info(f"[{self.session_id}] Preloading welcome speech TTS...")
            audio_base64 = await text_to_speech(clean_welcome, voice, tts_model)

            if audio_base64:
                # Store in Redis with special key
                r = await get_redis()
                cache_key = f"stream:{self.session_id}:welcome_speech"
                await r.hset(cache_key, mapping={
                    "text": welcome_text,
                    "audio_base64": audio_base64
                })
                await r.expire(cache_key, 3600)  # 1 hour TTL

                self.welcome_cached = True
                logger.info(f"[{self.session_id}] Welcome speech cached successfully")
                return True

        except Exception as e:
            logger.error(f"[{self.session_id}] Failed to preload welcome speech: {e}")

        return False

    async def get_welcome_speech(self) -> Optional[dict]:
        """
        Get cached welcome speech if available.

        Returns:
            Dict with text and audio_base64 if cached, None otherwise
        """
        from core.redis_client import get_redis

        try:
            r = await get_redis()
            cache_key = f"stream:{self.session_id}:welcome_speech"
            data = await r.hgetall(cache_key)

            if data and data.get("audio_base64"):
                logger.info(f"[{self.session_id}] Welcome speech retrieved from cache")
                return {
                    "text": data.get("text", ""),
                    "audio_base64": data["audio_base64"]
                }
        except Exception as e:
            logger.error(f"[{self.session_id}] Failed to get welcome speech: {e}")

        return None
