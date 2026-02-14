"""
Stream Buddy - AI Co-host for Streamers
FastAPI application entry point.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config cache
_config: dict | None = None


def load_config() -> dict:
    """Load configuration from config.json."""
    global _config
    if _config is None:
        config_path = Path(__file__).parent / "config.json"
        with open(config_path, "r") as f:
            _config = json.load(f)
    return _config


# Create FastAPI app
app = FastAPI(
    title="Stream Buddy",
    description="AI Co-host for Streamers",
    version="1.0.0"
)

# Import and include WebSocket router
from api.websocket import router as ws_router
app.include_router(ws_router)

# Import and include VTuber avatar WebSocket router
try:
    from vtuber_engine.websocket_handler import router as vtuber_ws_router
    app.include_router(vtuber_ws_router, tags=["vtuber"])
    logger.info("VTuber engine WebSocket router loaded")
except ImportError as e:
    logger.warning(f"VTuber engine not available: {e}")

# Serve static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Serve vtuber test directory (for development)
vtuber_path = Path(__file__).parent / "vtuber"
if vtuber_path.exists():
    app.mount("/vtuber", StaticFiles(directory=vtuber_path, html=True), name="vtuber")


@app.get("/")
async def root():
    """DEPRECATED: Use /obs/panel instead. Kept for backwards compatibility."""
    return FileResponse(static_path / "index.html")


@app.get("/outline/")
@app.get("/outline")
async def outline():
    """Serve the script outline pop-out page."""
    return FileResponse(static_path / "outline.html")


@app.get("/obs/overlay")
async def obs_overlay():
    """Serve the OBS overlay page (1080p transparent avatar only)."""
    return FileResponse(static_path / "obs-overlay.html")


@app.get("/obs/")
@app.get("/obs")
async def obs_panel():
    """Serve the OBS control panel page (settings, status, sections - no avatar)."""
    return FileResponse(static_path / "obs-panel.html")


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    config = load_config()
    return {
        "persona_name": config.get("persona", {}).get("name", "Buddy"),
        "script": config.get("script", []),
        "wake_phrases": config.get("triggers", {}).get("wake_phrases", [])
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/session/{session_id}/outline")
async def get_session_outline(session_id: str):
    """Get session outline (structure + progress) from Redis."""
    from core.redis_client import get_script_structure, get_session_state, get_prediction_status

    structure = await get_script_structure(session_id)
    state = await get_session_state(session_id)

    if not structure:
        return {"found": False}

    # Get covered sections from state (saved by websocket handler)
    sections_covered = state.get("all_sections_covered", []) if state else []
    keyword_progress = state.get("keyword_progress", {}) if state else {}

    # Get prediction cache status (if enabled)
    prediction_status = await get_prediction_status(session_id)
    predictions = prediction_status.get("predictions_by_section", {}) if prediction_status else {}

    return {
        "found": True,
        "structure": structure,
        "sections_covered": sections_covered,
        "keyword_progress": keyword_progress,
        "predictions": predictions
    }


@app.get("/api/session/{session_id}/cache-stats")
async def get_cache_stats(session_id: str):
    """Get prediction cache statistics for a session."""
    from core.redis_client import get_prediction_status, get_voice_cache_keywords

    prediction_status = await get_prediction_status(session_id)
    cached_keywords = await get_voice_cache_keywords(session_id)

    if not prediction_status:
        return {"enabled": False}

    return {
        "enabled": True,
        "status": prediction_status.get("status", "unknown"),
        "generated": prediction_status.get("generated", 0),
        "keywords": prediction_status.get("keywords", []),
        "cached_by_section": cached_keywords
    }


@app.delete("/api/session/{session_id}/cache")
async def clear_prediction_cache(session_id: str):
    """Clear prediction cache for a session."""
    from core.redis_client import get_redis

    r = await get_redis()

    # Clear voice cache entries
    voice_keys = await r.keys(f"stream:{session_id}:voice_cache:*")
    voice_count = len(voice_keys) if voice_keys else 0
    if voice_keys:
        await r.delete(*voice_keys)

    # Clear prediction status
    await r.delete(f"stream:{session_id}:prediction_status")

    logger.info(f"Cleared prediction cache for session {session_id}: {voice_count} entries")
    return {"cleared": voice_count}


class PasswordRequest(BaseModel):
    password: str


@app.post("/api/verify-password")
async def verify_password(request: PasswordRequest):
    """Verify demo password."""
    demo_password = os.getenv("DEMO_PASSWORD", "streambuddy2025")
    if request.password == demo_password:
        return {"valid": True}
    return {"valid": False}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    # Increase websocket ping timeout to handle long TTS streaming
    # Default is 20s ping interval + 20s timeout = 40s max
    # TTS can take 30+ seconds, so increase to prevent disconnects
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        ws_ping_interval=60.0,  # Send ping every 60s (default: 20s)
        ws_ping_timeout=60.0,   # Wait 60s for pong (default: 20s)
    )
