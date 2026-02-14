"""
Redis client for session and script storage.
"""
import os
import json
import redis.asyncio as redis

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True
        )
    return _redis


async def store_script(session_id: str, script: str) -> None:
    """Store raw script text for a session."""
    r = await get_redis()
    await r.set(f"stream:{session_id}:script", script, ex=86400)  # 24h TTL


async def get_script(session_id: str) -> str | None:
    """Get script for a session."""
    r = await get_redis()
    return await r.get(f"stream:{session_id}:script")


async def store_script_structure(session_id: str, structure: dict) -> None:
    """Store parsed script structure."""
    r = await get_redis()
    await r.set(f"stream:{session_id}:structure", json.dumps(structure), ex=86400)


async def get_script_structure(session_id: str) -> dict | None:
    """Get parsed script structure."""
    r = await get_redis()
    data = await r.get(f"stream:{session_id}:structure")
    return json.loads(data) if data else None


async def store_session_state(session_id: str, state: dict) -> None:
    """Store current session state (position, history, etc)."""
    r = await get_redis()
    await r.set(f"stream:{session_id}:state", json.dumps(state), ex=86400)


async def get_session_state(session_id: str) -> dict | None:
    """Get current session state."""
    r = await get_redis()
    data = await r.get(f"stream:{session_id}:state")
    return json.loads(data) if data else None


async def clear_session(session_id: str) -> None:
    """Clear all session data."""
    r = await get_redis()
    keys = await r.keys(f"stream:{session_id}:*")
    if keys:
        await r.delete(*keys)


# Voice Cache functions for Prediction Cache feature
async def store_voice_cache(
    session_id: str,
    section_id: int,
    keyword: str,
    response_text: str,
    audio_base64: str
) -> None:
    """
    Store pre-generated TTS audio for a predicted keyword response.

    Key pattern: stream:{session_id}:voice_cache:{section_id}:{keyword_hash}
    TTL: 1 hour (auto-cleanup)
    """
    import hashlib
    r = await get_redis()
    keyword_hash = hashlib.md5(keyword.lower().encode()).hexdigest()[:8]
    key = f"stream:{session_id}:voice_cache:{section_id}:{keyword_hash}"

    data = {
        "keyword": keyword,
        "response_text": response_text,
        "audio_base64": audio_base64,
        "section_id": section_id
    }
    await r.set(key, json.dumps(data), ex=3600)  # 1 hour TTL


async def get_voice_cache(session_id: str, cache_key: str) -> dict | None:
    """
    Get cached voice data by cache key.

    Args:
        session_id: Session identifier
        cache_key: Format "section_id:keyword_hash"

    Returns:
        Dict with keyword, response_text, audio_base64 or None
    """
    r = await get_redis()
    key = f"stream:{session_id}:voice_cache:{cache_key}"
    data = await r.get(key)
    return json.loads(data) if data else None


async def delete_section_cache(session_id: str, section_id: int) -> int:
    """
    Delete all voice cache entries for a section.

    Args:
        session_id: Session identifier
        section_id: Section ID to cleanup

    Returns:
        Number of keys deleted
    """
    r = await get_redis()
    pattern = f"stream:{session_id}:voice_cache:{section_id}:*"
    keys = await r.keys(pattern)
    if keys:
        return await r.delete(*keys)
    return 0


async def get_voice_cache_keywords(session_id: str) -> dict:
    """
    Get all cached keywords grouped by section.

    Returns:
        Dict of {section_id: [{keyword, response_text}]}
    """
    r = await get_redis()
    pattern = f"stream:{session_id}:voice_cache:*"
    keys = await r.keys(pattern)

    by_section = {}
    for key in keys:
        data = await r.get(key)
        if data:
            entry = json.loads(data)
            section_id = entry.get("section_id", 0)
            if section_id not in by_section:
                by_section[section_id] = []
            by_section[section_id].append({
                "keyword": entry.get("keyword"),
                "response_text": entry.get("response_text", "")[:50]  # Truncate for display
            })

    return by_section


async def store_prediction_status(session_id: str, status: dict) -> None:
    """Store prediction cache status for UI display."""
    r = await get_redis()
    await r.set(f"stream:{session_id}:prediction_status", json.dumps(status), ex=3600)


async def get_prediction_status(session_id: str) -> dict | None:
    """Get prediction cache status."""
    r = await get_redis()
    data = await r.get(f"stream:{session_id}:prediction_status")
    return json.loads(data) if data else None
