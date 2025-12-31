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


@app.get("/")
async def root():
    """Serve the main HTML page."""
    return FileResponse(static_path / "index.html")


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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
