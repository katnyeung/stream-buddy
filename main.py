"""
Stream Buddy - AI Co-host for Streamers
FastAPI application entry point.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Load environment variables
load_dotenv()

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

# Serve static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Serve vtuber test directory (for development)
vtuber_path = Path(__file__).parent / "vtuber"
if vtuber_path.exists():
    app.mount("/vtuber", StaticFiles(directory=vtuber_path, html=True), name="vtuber")


@app.get("/")
async def root():
    """Serve the main HTML page."""
    return FileResponse(static_path / "index.html")


@app.get("/outline/")
@app.get("/outline")
async def outline():
    """Serve the script outline pop-out page."""
    return FileResponse(static_path / "outline.html")


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
    from core.redis_client import get_script_structure, get_session_state

    structure = await get_script_structure(session_id)
    state = await get_session_state(session_id)

    if not structure:
        return {"found": False}

    # Get covered sections from state (saved by websocket handler)
    sections_covered = state.get("all_sections_covered", []) if state else []

    return {
        "found": True,
        "structure": structure,
        "sections_covered": sections_covered
    }


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
    uvicorn.run(app, host="0.0.0.0", port=port)
