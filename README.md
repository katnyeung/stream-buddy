# Stream Buddy - AI Co-Host for Live Streaming

An intelligent AI co-host that listens to your live stream, understands context, and contributes meaningful insights in real-time. Like having a knowledgeable friend who helps you present.

**Live Demo:** [https://resumebuddy.cv/stream-buddy/](https://resumebuddy.cv/stream-buddy/)

---

## The Problem

Live streaming alone is challenging:
- Hard to maintain energy and fill dead air
- Easy to forget talking points under pressure
- No one to bounce ideas off or add context
- Viewers disengage during solo monologues

## The Solution

Stream Buddy acts as your AI co-host that:
- **Listens** to your stream in real-time via speech-to-text
- **Understands** your script and tracks progress
- **Enriches** your points with relevant facts and context
- **Speaks** naturally using cloned or selected voices
- **Adapts** to your style (aggressive, balanced, passive)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROWSER (Frontend)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ Microphone  │  │   Script    │  │  Settings   │  │   Audio    │ │
│  │   Input     │  │   Outline   │  │   Panel     │  │  Playback  │ │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └──────▲─────┘ │
│         │              WebSocket (Real-time)                │       │
└─────────┼───────────────────────────────────────────────────┼───────┘
          │                                                   │
          ▼                                                   │
┌─────────────────────────────────────────────────────────────────────┐
│                       FASTAPI SERVER (Backend)                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    WebSocket Handler                          │  │
│  │  • Receives audio chunks (100ms intervals)                    │  │
│  │  • Manages session state                                      │  │
│  │  • Orchestrates AI pipeline                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│         │                    │                      │               │
│         ▼                    ▼                      ▼               │
│  ┌────────────┐      ┌─────────────┐       ┌─────────────┐         │
│  │   OpenAI   │      │   Google    │       │  ElevenLabs │         │
│  │  Whisper   │ ───▶ │   Gemini    │ ───▶  │     TTS     │         │
│  │   (STT)    │      │   (Brain)   │       │   (Voice)   │         │
│  └────────────┘      └─────────────┘       └─────────────┘         │
│                              │                                      │
│                              ▼                                      │
│                      ┌─────────────┐                               │
│                      │    Redis    │                               │
│                      │  (Session)  │                               │
│                      └─────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Real-Time Processing Flow

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  USER   │    │ WHISPER │    │ GEMINI  │    │ ELEVEN  │    │  USER   │
│ SPEAKS  │───▶│   STT   │───▶│  BRAIN  │───▶│  LABS   │───▶│ HEARS   │
│         │    │         │    │         │    │   TTS   │    │ BUDDY   │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
   Audio         Text          Decision       Audio          Playback
  Stream       Transcript      + Response     Base64

Timeline: ~2-4 seconds end-to-end latency
```

### Processing Steps

1. **Audio Capture** (Browser)
   - Continuous microphone recording via MediaRecorder API
   - WebM/Opus codec at 100ms chunks
   - Echo cancellation & noise suppression enabled

2. **Speech-to-Text** (OpenAI Whisper)
   - Accumulates 15 seconds of audio before transcription
   - Minimum 50KB audio (~5s of speech) required
   - Context-aware transcription for technical terms

3. **Brain Decision** (Google Gemini)
   - Analyzes transcript against script outline
   - Decides action: `enrich`, `remind`, `respond`, or `wait`
   - Tracks conversation history to avoid repetition
   - Personality-aware responses (supportive/neutral/skeptical)

4. **Text-to-Speech** (ElevenLabs)
   - Multiple voice options (male/female, various styles)
   - Three quality tiers: Flash (fast), Turbo (balanced), Premium (expressive)
   - Premium model supports emotional speech

5. **Audio Playback** (Browser)
   - Base64 MP3 decoded and played
   - Automatic buffer clearing to prevent echo
   - Ready signal sent when playback completes

---

## Features

### Co-Host Behaviors

| Action | Trigger | Output |
|--------|---------|--------|
| **Enrich** | Speaker makes a point worth expanding | Adds relevant fact/context (verbal) |
| **Remind** | Topic covered, suggest next | Visual prompt update |
| **Respond** | Speaker asks directly ("What do you think?") | Full conversational response |
| **Wait** | Speaker is flowing well | Stay quiet, listen |

### Customization Options

| Setting | Options | Description |
|---------|---------|-------------|
| **Voice** | 8 voices | Rachel, Bella, Antoni, Josh, Adam, Sam, Aria, Daniel |
| **Engagement** | Aggressive / Balanced / Passive | How often Buddy speaks up |
| **Personality** | Supportive / Neutral / Skeptical | Tone of responses |
| **Quality** | Flash / Turbo / Premium | TTS model (speed vs expressiveness) |

### Smart Features

- **Script Parsing**: Automatically extracts sections and key points from your outline
- **Progress Tracking**: Visual checklist shows completed topics
- **Repetition Blocking**: Prevents Buddy from saying the same thing twice
- **Cooldown System**: Style-based timing between interventions
- **Session Persistence**: Settings saved to localStorage

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Frontend** | Vanilla JS, HTML5, CSS3 | UI, audio capture, WebSocket client |
| **Backend** | FastAPI, Python 3.10+ | WebSocket server, API orchestration |
| **STT** | OpenAI Whisper API | Speech-to-text transcription |
| **LLM** | Google Gemini 2.0 Flash | Context understanding, decision making |
| **TTS** | ElevenLabs API | Natural voice synthesis |
| **State** | Redis | Session storage, script caching |
| **Deploy** | AWS Lightsail, Nginx, Systemd | Production hosting |

---

## Quick Start

### Prerequisites
- Python 3.10+
- Redis server
- API Keys: OpenAI, Google Gemini, ElevenLabs

### Installation

```bash
# Clone repository
git clone https://github.com/your-repo/stream-buddy.git
cd stream-buddy

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Run Locally

```bash
# Start Redis (if not running)
redis-server

# Start application
python main.py
```

Open http://localhost:8000 in your browser.

---

## Configuration

### Environment Variables

```env
# Required
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AI...
ELEVENLABS_API_KEY=...

# Optional
ELEVENLABS_VOICE_CIPHER=...    # Custom cloned voice ID
ELEVENLABS_VOICE_NARRATOR=...  # Custom cloned voice ID
REDIS_HOST=localhost
REDIS_PORT=6379
PORT=8000
```

### Timing Configuration (websocket.py)

```python
TRANSCRIBE_INTERVAL_MS = 15000  # Transcribe every 15 seconds
MIN_AUDIO_BYTES = 50000         # Minimum audio to process (~5s)
MIN_WORDS_FOR_BRAIN = 20        # Words needed before brain analysis

# Cooldowns by engagement style
COOLDOWNS = {
    "aggressive": {"enrich": 20000, "remind": 15000},
    "balanced": {"enrich": 45000, "remind": 30000},
    "passive": {"enrich": 120000, "remind": 60000}
}
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main application UI |
| `/ws/stream` | WebSocket | Real-time audio streaming |
| `/api/config` | GET | Get persona configuration |
| `/health` | GET | Health check |

### WebSocket Messages

**Client → Server:**
```json
{"type": "load_script", "script": "...", "voice": "...", "style": "...", "personality": "...", "tts_model": "..."}
{"type": "ready_for_audio"}
{"type": "reset"}
// Binary: audio chunks
```

**Server → Client:**
```json
{"type": "ready", "session_id": "...", "persona_name": "Buddy"}
{"type": "script_loaded", "structure": {...}, "initial_prompt": "..."}
{"type": "transcript", "text": "...", "word_count": 42}
{"type": "cohost_speaking", "text": "...", "reason": "..."}
{"type": "cohost_audio", "text": "...", "audio_base64": "..."}
{"type": "sections_progress", "sections_covered": [1, 2]}
{"type": "show_prompt", "text": "..."}
```

---

## Project Structure

```
stream-buddy/
├── main.py                 # FastAPI entry point
├── config.json             # Persona configuration
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
│
├── api/
│   └── websocket.py        # WebSocket handler, main loop
│
├── core/
│   ├── audio_buffer.py     # Audio accumulation
│   ├── stt_client.py       # OpenAI Whisper client
│   ├── tts_client.py       # ElevenLabs client
│   ├── script_manager.py   # Gemini brain, script parsing
│   └── redis_client.py     # Session state management
│
├── static/
│   ├── index.html          # Main UI
│   └── js/
│       └── app.js          # Frontend application
│
└── deploy/
    ├── deploy.sh               # Deployment script
    ├── stream-buddy.service    # Systemd service
    ├── nginx-stream-buddy.conf # Nginx config
    └── DEPLOYMENT.md           # Deployment guide
```

---

## Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full instructions.

**Quick Deploy:**
```bash
./deploy.sh
```

---

## Future Improvements

- [ ] Multi-language support
- [ ] Custom voice cloning integration
- [ ] OBS integration via Browser Source
- [ ] Viewer chat integration (Twitch/YouTube)
- [ ] Real-time sentiment analysis
- [ ] Automated highlight detection

---

## License

MIT License

---

## Acknowledgments

Built for hackathon demonstration. Powered by:
- [OpenAI Whisper](https://openai.com/research/whisper) - Speech recognition
- [Google Gemini](https://deepmind.google/technologies/gemini/) - Language understanding
- [ElevenLabs](https://elevenlabs.io/) - Voice synthesis
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
