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
