/**
 * Stream Buddy OBS App - Full session controller for 1080p OBS canvas
 * Mirrors the main app.js functionality but uses the OBS avatar renderer
 */

// VAD Constants
const DEFAULT_PAUSE_DURATION = 2000;
const MAX_SPEECH_DURATION = 30000;
const SILENCE_THRESHOLD = 8;
const VAD_CHECK_INTERVAL = 100;
const BUDDY_TEXT_TTL_MS = 5000;

/**
 * AudioQueue - Manages TTS playback queue
 */
class AudioQueue {
    constructor(app) {
        this.app = app;
        this.queue = [];
        this.isPlaying = false;
        this.clearTextTimeout = null;
    }

    enqueue(audioBase64, text, actions) {
        console.log('[AudioQueue] Enqueuing audio, queue size:', this.queue.length + 1);
        this.queue.push({ audio: audioBase64, text, actions });
        if (!this.isPlaying) {
            this.playNext();
        }
    }

    playNext() {
        if (this.queue.length === 0) {
            console.log('[AudioQueue] Queue empty, signaling ready');
            this.isPlaying = false;

            if (this.clearTextTimeout) clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = setTimeout(() => {
                this.app.buddyText.innerHTML = '';
                this.app.buddyText.classList.remove('speaking');
                this.clearTextTimeout = null;
            }, BUDDY_TEXT_TTL_MS);

            if (this.app.ws && this.app.ws.readyState === WebSocket.OPEN) {
                this.app.ws.send(JSON.stringify({ type: 'ready_for_audio' }));
            }
            this.app.resumeVAD();
            return;
        }

        if (this.clearTextTimeout) {
            clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = null;
        }

        this.isPlaying = true;
        const item = this.queue.shift();
        console.log('[AudioQueue] Playing next item, remaining:', this.queue.length);
        this.app.playSingleAudio(item.audio, item.text, item.actions, () => {
            this.playNext();
        });
    }

    clear() {
        this.queue = [];
        this.isPlaying = false;
        if (this.clearTextTimeout) {
            clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = null;
        }
        this.app.buddyText.innerHTML = '';
        this.app.buddyText.classList.remove('speaking');
    }

    get length() {
        return this.queue.length;
    }
}

/**
 * OBS Stream Buddy App
 */
class OBSStreamBuddy {
    constructor() {
        this.ws = null;
        this.isConnected = false;
        this.sessionId = null;
        this.personaName = 'Buddy';

        // Audio recording
        this.mediaRecorder = null;
        this.audioStream = null;
        this.isRecording = false;

        // Audio playback
        this.isPlaying = false;
        this.currentAudioElement = null;
        this.scheduledActionTimeouts = [];

        // Timer
        this.timerSeconds = 0;
        this.timerRunning = false;
        this.timerInterval = null;

        // Avatar (OBSAvatar instance)
        this.obsAvatar = null;

        // Action system
        this.actionParser = null;
        this.actionLibrary = null;
        this.actionExecutor = null;
        this.pendingActions = null;

        // VAD
        this.vadInterval = null;
        this.lastSpeechTime = 0;
        this.speechStartTime = 0;
        this.vadEnabled = false;
        this.inputAnalyser = null;
        this.inputAudioContext = null;
        this.pauseDuration = DEFAULT_PAUSE_DURATION;

        // Audio Queue
        this.audioQueue = new AudioQueue(this);

        // Sections
        this.sections = [];
        this.currentSection = 0;
        this.completedSections = new Set();

        this.init();
    }

    init() {
        // Main container and panels
        this.mainContainer = document.getElementById('main-container');
        this.setupPanel = document.getElementById('setup-panel');
        this.scriptInput = document.getElementById('script-input');
        this.voiceSelect = document.getElementById('voice-select');
        this.styleSelect = document.getElementById('style-select');
        this.personalitySelect = document.getElementById('personality-select');
        this.ttsModelSelect = document.getElementById('tts-model-select');
        this.startBtn = document.getElementById('start-btn');
        this.pauseDurationSelect = document.getElementById('pause-duration');
        this.periodicIntervalSelect = document.getElementById('periodic-interval');

        // OBS screen elements
        this.buddyText = document.getElementById('buddy-text');
        this.statusDot = document.getElementById('status-dot');
        this.statusText = document.getElementById('status-text');
        this.progressFill = document.getElementById('progress-fill');
        this.sectionInfo = document.getElementById('section-info');
        this.progressPercent = document.getElementById('progress-percent');
        this.sectionsList = document.getElementById('sections-list');
        this.timerDisplay = document.getElementById('timer-display');
        this.timerBtn = document.getElementById('timer-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.resetBtn = document.getElementById('reset-btn');

        // Load saved settings
        this.loadSettings();

        // Event listeners
        this.startBtn.addEventListener('click', () => this.startSession());
        this.stopBtn.addEventListener('click', () => this.stopSession());
        this.resetBtn.addEventListener('click', () => this.resetSession());
        this.timerBtn.addEventListener('click', () => this.toggleTimer());

        // Save settings on change
        [this.voiceSelect, this.styleSelect, this.personalitySelect, this.ttsModelSelect].forEach(el => {
            el.addEventListener('change', () => this.saveSettings());
        });

        if (this.pauseDurationSelect) {
            this.pauseDurationSelect.addEventListener('change', (e) => {
                this.pauseDuration = parseInt(e.target.value) || DEFAULT_PAUSE_DURATION;
            });
        }

        console.log('[OBSStreamBuddy] Initialized');
    }

    async startSession() {
        const script = this.scriptInput.value.trim();
        if (!script) {
            alert('Please enter a script first');
            return;
        }

        this.selectedVoice = this.voiceSelect.value;
        this.selectedStyle = this.styleSelect.value;
        this.selectedPersonality = this.personalitySelect.value;
        this.selectedTtsModel = this.ttsModelSelect.value;
        this.pauseDuration = parseInt(this.pauseDurationSelect?.value) || DEFAULT_PAUSE_DURATION;
        this.periodicInterval = parseInt(this.periodicIntervalSelect?.value) || 5;

        try {
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            console.log('[OBSStreamBuddy] Microphone access granted');
            this.connectWebSocket(script);

            // Hide setup panel, show session UI
            this.mainContainer.classList.add('session-active');

            // Avatar is already initialized, just connect
            this.initOBSAvatar();

        } catch (err) {
            console.error('[OBSStreamBuddy] Failed to start session:', err);
            alert('Failed to access microphone. Please allow microphone access.');
        }
    }

    initOBSAvatar() {
        // OBSAvatar is auto-initialized on DOM load, get the instance
        if (window.obsAvatar) {
            this.obsAvatar = window.obsAvatar;

            // Get action system from avatar
            if (this.obsAvatar.actionParser) {
                this.actionParser = this.obsAvatar.actionParser;
            }
            if (this.obsAvatar.actionLibrary) {
                this.actionLibrary = this.obsAvatar.actionLibrary;
            }
            if (this.obsAvatar.actionExecutor) {
                this.actionExecutor = this.obsAvatar.actionExecutor;
            }

            console.log('[OBSStreamBuddy] OBS Avatar connected');
        } else {
            console.warn('[OBSStreamBuddy] OBS Avatar not available');
        }
    }

    stopSession() {
        console.log('[OBSStreamBuddy] Stopping session...');

        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
        }

        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        this.pauseTimer();
        this.mainContainer.classList.remove('session-active');
        this.setStatus('idle', 'Stopped');
    }

    resetSession() {
        console.log('[OBSStreamBuddy] Resetting session...');

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'reset' }));
        }

        this.buddyText.innerHTML = '';
        this.progressFill.style.width = '0%';
        this.sectionInfo.textContent = 'Section 0';
        this.progressPercent.textContent = '0%';

        this.currentSection = 0;
        this.completedSections = new Set();
        this.renderSections();
        this.resetTimer();
    }

    connectWebSocket(script) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const basePath = window.location.pathname.replace(/\/$/, '').replace(/\/obs\.html$/, '').replace(/\/obs$/, '');
        const wsUrl = `${protocol}//${window.location.host}${basePath}/ws/stream`;

        console.log('[OBSStreamBuddy] Connecting to:', wsUrl);

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('[OBSStreamBuddy] WebSocket connected');
            this.isConnected = true;
            this.setStatus('connected', 'Loading script...');
        };

        this.ws.onclose = () => {
            console.log('[OBSStreamBuddy] WebSocket disconnected');
            this.isConnected = false;
            this.setStatus('disconnected', 'Disconnected');
        };

        this.ws.onerror = (err) => {
            console.error('[OBSStreamBuddy] WebSocket error:', err);
        };

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            this.handleMessage(msg, script);
        };
    }

    handleMessage(msg, script) {
        switch (msg.type) {
            case 'ready':
                this.sessionId = msg.session_id;
                this.personaName = msg.persona_name;
                localStorage.setItem('streambuddy_session_id', this.sessionId);
                console.log(`[OBSStreamBuddy] Session: ${this.sessionId}`);

                // Reconnect avatar to this session
                if (this.obsAvatar) {
                    this.obsAvatar.avatarId = this.sessionId;
                    if (this.obsAvatar.ws) {
                        this.obsAvatar.ws.close();
                    }
                    this.obsAvatar.reconnectAttempts = 0;
                    this.obsAvatar.connectServer(this.sessionId);
                }

                this.ws.send(JSON.stringify({
                    type: 'load_script',
                    script: script,
                    voice: this.selectedVoice,
                    style: this.selectedStyle,
                    personality: this.selectedPersonality,
                    tts_model: this.selectedTtsModel
                }));
                break;

            case 'script_loaded':
                console.log('[OBSStreamBuddy] Script loaded');
                this.sections = msg.structure?.sections || [];
                this.currentSection = 0;
                this.completedSections = new Set();
                this.renderSections();
                this.setStatus('listening', 'Listening...');
                this.startRecording();

                this.ws.send(JSON.stringify({
                    type: 'set_auto_response',
                    enabled: true
                }));
                this.ws.send(JSON.stringify({
                    type: 'set_periodic_interval',
                    seconds: this.periodicInterval
                }));

                // Connect OBS avatar to server for Redis backbone control
                // This enables server-sent idle behaviors (idle_sway, idle_breathe, blink)
                if (this.obsAvatar && this.sessionId) {
                    console.log('[OBSStreamBuddy] Connecting avatar to Redis backbone...');
                    this.obsAvatar.connectServer(this.sessionId);
                }
                break;

            case 'transcript':
                console.log('[OBSStreamBuddy] Transcript:', msg.text);
                this.setStatus('listening', 'Listening...');
                break;

            case 'sections_progress':
                this.updateSectionProgress(msg.sections_covered);
                break;

            case 'cohost_speaking':
                console.log('[OBSStreamBuddy] Co-host preparing');
                let displayText = msg.text;
                this.pendingActions = null;

                if (this.actionParser && this.actionExecutor) {
                    const parsed = this.actionParser.parseWithTiming(msg.text, 60);
                    displayText = parsed.cleanText;
                    if (parsed.actions.length > 0) {
                        this.pendingActions = parsed.actions;
                    }
                }

                this.buddyText.innerHTML = '';
                this.buddyText.classList.add('speaking');
                this.setStatus('speaking', 'Speaking...');
                break;

            case 'cohost_audio':
                console.log('[OBSStreamBuddy] Audio received (legacy)');
                this.pauseVAD();
                if (msg.audio_base64) {
                    this.playAudio(msg.audio_base64);
                }
                break;

            case 'cohost_audio_queued':
                console.log('[OBSStreamBuddy] Audio queued');
                this.pauseVAD();

                let queuedDisplayText = msg.text;
                let queuedActions = null;

                if (this.actionParser) {
                    const parsed = this.actionParser.parseWithTiming(msg.text, 60);
                    queuedDisplayText = parsed.cleanText;
                    queuedActions = parsed.actions;
                }

                if (this.audioQueue.length === 0 && !this.audioQueue.isPlaying) {
                    this.buddyText.innerHTML = '';
                    this.buddyText.classList.add('speaking');
                }

                this.setStatus('speaking', 'Speaking...');

                if (msg.audio_base64) {
                    this.audioQueue.enqueue(msg.audio_base64, queuedDisplayText, queuedActions);
                }
                break;

            case 'progress':
                this.updateProgress(msg.section, msg.progress);
                break;

            case 'reset_complete':
                this.setStatus('listening', 'Reset complete');
                break;
        }
    }

    startRecording() {
        if (!this.audioStream || this.isRecording) return;

        this.mediaRecorder = new MediaRecorder(this.audioStream, {
            mimeType: 'audio/webm;codecs=opus'
        });

        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(event.data);
            }
        };

        this.mediaRecorder.start(100);
        this.isRecording = true;
        this.startVAD();
        console.log('[OBSStreamBuddy] Recording started');
    }

    // VAD methods
    initVAD() {
        if (!this.audioStream) return;

        try {
            this.inputAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.inputAudioContext.createMediaStreamSource(this.audioStream);
            this.inputAnalyser = this.inputAudioContext.createAnalyser();
            this.inputAnalyser.fftSize = 256;
            source.connect(this.inputAnalyser);
        } catch (err) {
            console.error('[VAD] Failed to initialize:', err);
        }
    }

    checkVoiceActivity() {
        if (!this.inputAnalyser || !this.vadEnabled) return;

        const dataArray = new Uint8Array(this.inputAnalyser.frequencyBinCount);
        this.inputAnalyser.getByteFrequencyData(dataArray);

        const sum = dataArray.reduce((a, b) => a + b, 0);
        const rms = Math.sqrt(sum / dataArray.length) * 100;
        const isSpeaking = rms >= SILENCE_THRESHOLD;
        const now = Date.now();

        if (isSpeaking) {
            if (this.speechStartTime === 0) {
                this.speechStartTime = now;
            }
            this.lastSpeechTime = now;

            const speechDuration = now - this.speechStartTime;
            if (speechDuration >= MAX_SPEECH_DURATION) {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'transcribe_now' }));
                }
                this.speechStartTime = now;
                this.lastSpeechTime = now;
            }
        } else {
            const silenceDuration = now - this.lastSpeechTime;
            if (silenceDuration >= this.pauseDuration && this.lastSpeechTime > 0 && this.speechStartTime > 0) {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'transcribe_now' }));
                }
                this.speechStartTime = 0;
                this.lastSpeechTime = now;
            }
        }
    }

    startVAD() {
        if (this.vadInterval) return;
        this.initVAD();
        this.vadEnabled = true;
        this.lastSpeechTime = Date.now();
        this.vadInterval = setInterval(() => this.checkVoiceActivity(), VAD_CHECK_INTERVAL);
    }

    stopVAD() {
        this.vadEnabled = false;
        if (this.vadInterval) {
            clearInterval(this.vadInterval);
            this.vadInterval = null;
        }
    }

    resumeVAD() {
        if (!this.vadInterval) return;
        this.vadEnabled = true;
        this.lastSpeechTime = Date.now();
        this.speechStartTime = 0;
    }

    pauseVAD() {
        this.vadEnabled = false;
    }

    // Audio playback - delegates to OBSAvatar to avoid echo
    playAudio(base64Audio) {
        this.isPlaying = true;

        // Send audio to avatar for playback + lip sync (single audio source)
        if (this.obsAvatar) {
            this.obsAvatar.playTTSAudio(base64Audio, () => {
                // Callback when audio ends
                this.isPlaying = false;
                this.currentAudioElement = null;
                this.setStatus('listening', 'Listening...');
                this.resumeVAD();

                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'ready_for_audio' }));
                }
            });
        }

        if (this.pendingActions && this.actionParser && this.actionExecutor) {
            this.cancelScheduledActions();
            this.scheduledActionTimeouts = this.actionParser.scheduleActions(
                this.pendingActions,
                (type, name, params) => {
                    this.actionExecutor.executeFromParsed({ type, name, params: params || {} });
                }
            );
            this.pendingActions = null;
        }
    }

    playSingleAudio(base64Audio, text, actions, onComplete) {
        this.isPlaying = true;

        // Display text
        const sentenceEl = document.createElement('span');
        sentenceEl.className = 'buddy-sentence current';
        sentenceEl.textContent = text;
        this.buddyText.appendChild(sentenceEl);

        // Send to avatar for playback + lip sync (single audio source to avoid echo)
        if (this.obsAvatar) {
            this.obsAvatar.playTTSAudio(base64Audio, () => {
                // Callback when audio ends
                this.isPlaying = false;
                this.currentAudioElement = null;
                sentenceEl.classList.remove('current');
                if (onComplete) onComplete();
            });
        } else {
            // Fallback if no avatar - play locally
            const audio = new Audio('data:audio/mp3;base64,' + base64Audio);
            audio.volume = 0.8;
            audio.onended = () => {
                this.isPlaying = false;
                sentenceEl.classList.remove('current');
                if (onComplete) onComplete();
            };
            audio.onerror = () => {
                this.isPlaying = false;
                this.cancelScheduledActions();
                if (onComplete) onComplete();
            };
            audio.play().catch(() => {
                this.isPlaying = false;
                this.cancelScheduledActions();
                if (onComplete) onComplete();
            });
        }

        if (actions && actions.length > 0 && this.actionParser && this.actionExecutor) {
            this.cancelScheduledActions();
            this.scheduledActionTimeouts = this.actionParser.scheduleActions(
                actions,
                (type, name, params) => {
                    this.actionExecutor.executeFromParsed({ type, name, params: params || {} });
                }
            );
        }
    }

    cancelScheduledActions() {
        if (this.actionParser && this.scheduledActionTimeouts.length > 0) {
            this.actionParser.cancelScheduled(this.scheduledActionTimeouts);
            this.scheduledActionTimeouts = [];
        }
    }

    // UI methods
    setStatus(state, text) {
        this.statusDot.className = 'status-dot';
        if (state === 'connected' || state === 'listening') {
            this.statusDot.classList.add('connected');
        } else if (state === 'speaking') {
            this.statusDot.classList.add('speaking');
        }
        this.statusText.textContent = text;
    }

    updateProgress(section, progress) {
        this.sectionInfo.textContent = `Section ${section}`;
        this.progressPercent.textContent = `${Math.round(progress)}%`;
        this.progressFill.style.width = `${progress}%`;
    }

    renderSections() {
        if (!this.sections.length) {
            this.sectionsList.innerHTML = '<li class="section-item">No sections</li>';
            return;
        }

        this.sectionsList.innerHTML = this.sections.map((section, index) => {
            let stateClass = 'upcoming';
            if (this.completedSections.has(index)) {
                stateClass = 'completed';
            } else if (index === this.currentSection) {
                stateClass = 'current';
            }

            return `
                <li class="section-item ${stateClass}">
                    <span class="section-number">${index + 1}</span>
                    ${section.title}
                </li>
            `;
        }).join('');

        const completed = this.completedSections.size;
        const total = this.sections.length;
        const progress = total > 0 ? (completed / total) * 100 : 0;
        this.progressFill.style.width = `${progress}%`;
        this.progressPercent.textContent = `${Math.round(progress)}%`;
        this.sectionInfo.textContent = `Section ${this.currentSection + 1} of ${total}`;
    }

    updateSectionProgress(sectionsCovered) {
        if (!sectionsCovered || !this.sections.length) return;

        sectionsCovered.forEach(sectionNum => {
            const index = sectionNum - 1;
            if (index >= 0 && index < this.sections.length) {
                this.completedSections.add(index);
            }
        });

        for (let i = 0; i < this.sections.length; i++) {
            if (!this.completedSections.has(i)) {
                this.currentSection = i;
                break;
            }
        }

        this.renderSections();
    }

    // Timer
    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    toggleTimer() {
        if (this.timerRunning) {
            this.pauseTimer();
        } else {
            this.startTimer();
        }
    }

    startTimer() {
        this.timerRunning = true;
        this.timerBtn.textContent = 'Pause';
        this.timerBtn.classList.remove('start');
        this.timerBtn.classList.add('pause');
        this.timerDisplay.classList.add('running');

        this.timerInterval = setInterval(() => {
            this.timerSeconds++;
            this.timerDisplay.textContent = this.formatTime(this.timerSeconds);
        }, 1000);
    }

    pauseTimer() {
        this.timerRunning = false;
        this.timerBtn.textContent = 'Start';
        this.timerBtn.classList.remove('pause');
        this.timerBtn.classList.add('start');
        this.timerDisplay.classList.remove('running');

        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    resetTimer() {
        this.pauseTimer();
        this.timerSeconds = 0;
        this.timerDisplay.textContent = '00:00';
    }

    // Settings persistence
    loadSettings() {
        try {
            const saved = localStorage.getItem('streambuddy_settings');
            if (saved) {
                const settings = JSON.parse(saved);
                if (settings.voice) this.voiceSelect.value = settings.voice;
                if (settings.style) this.styleSelect.value = settings.style;
                if (settings.personality) this.personalitySelect.value = settings.personality;
                if (settings.ttsModel) this.ttsModelSelect.value = settings.ttsModel;
            }
        } catch (e) {
            console.warn('[OBSStreamBuddy] Failed to load settings:', e);
        }
    }

    saveSettings() {
        try {
            const settings = {
                voice: this.voiceSelect.value,
                style: this.styleSelect.value,
                personality: this.personalitySelect.value,
                ttsModel: this.ttsModelSelect.value
            };
            localStorage.setItem('streambuddy_settings', JSON.stringify(settings));
        } catch (e) {
            console.warn('[OBSStreamBuddy] Failed to save settings:', e);
        }
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('[OBSStreamBuddy] DOM loaded, initializing...');
    window.obsStreamBuddy = new OBSStreamBuddy();

    // Check for overlay mode (?overlay=true)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('overlay') === 'true') {
        document.body.classList.add('overlay-mode');
        console.log('[OBSStreamBuddy] Overlay mode enabled - avatar only');

        // Auto-connect to avatar WebSocket for server commands
        // Wait for avatar to initialize, then connect
        setTimeout(() => {
            if (window.obsAvatar) {
                const sessionId = urlParams.get('session') || localStorage.getItem('streambuddy_session_id') || 'buddy';
                window.obsAvatar.connectServer(sessionId);
                console.log(`[OBSStreamBuddy] Overlay auto-connected to session: ${sessionId}`);
            }
        }, 1000);
    }
});
