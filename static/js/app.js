/**
 * Stream Buddy - Frontend Application
 * Continuous streaming - server handles transcription timing
 */

class StreamBuddy {
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

        // Timer
        this.timerSeconds = 0;
        this.timerRunning = false;
        this.timerInterval = null;

        this.init();
    }

    init() {
        // Setup screen elements
        this.setupScreen = document.getElementById('setup-screen');
        this.mainScreen = document.getElementById('main-screen');
        this.scriptInput = document.getElementById('script-input');
        this.voiceSelect = document.getElementById('voice-select');
        this.styleSelect = document.getElementById('style-select');
        this.personalitySelect = document.getElementById('personality-select');
        this.ttsModelSelect = document.getElementById('tts-model-select');
        this.startBtn = document.getElementById('start-btn');

        // Load saved settings from localStorage
        this.loadSettings();

        // Save settings on change
        this.voiceSelect.addEventListener('change', () => this.saveSettings());
        this.styleSelect.addEventListener('change', () => this.saveSettings());
        this.personalitySelect.addEventListener('change', () => this.saveSettings());
        this.ttsModelSelect.addEventListener('change', () => this.saveSettings());

        // Main screen elements
        this.sectionsList = document.getElementById('sections-list');
        this.buddyText = document.getElementById('buddy-text');
        this.buddyPanel = document.querySelector('.buddy-panel');
        this.progressFill = document.getElementById('progress-fill');

        // Script structure
        this.sections = [];
        this.currentSection = 0;
        this.completedSections = new Set();
        this.sectionInfo = document.getElementById('section-info');
        this.progressPercent = document.getElementById('progress-percent');
        this.transcriptList = document.getElementById('transcript-list');
        this.statusIcon = document.getElementById('status-icon');
        this.statusBadge = document.getElementById('status-badge');
        this.statusText = document.getElementById('status-text');
        this.stopBtn = document.getElementById('stop-btn');
        this.resetBtn = document.getElementById('reset-btn');

        // Timer elements
        this.timerDisplay = document.getElementById('timer-display');
        this.timerBtn = document.getElementById('timer-btn');

        // Event listeners
        this.startBtn.addEventListener('click', () => this.startSession());
        this.stopBtn.addEventListener('click', () => this.stopSession());
        this.resetBtn.addEventListener('click', () => this.resetSession());
        this.timerBtn.addEventListener('click', () => this.toggleTimer());

        console.log('[StreamBuddy] Initialized');
    }

    async startSession() {
        const script = this.scriptInput.value.trim();
        if (!script) {
            alert('Please enter a script first');
            return;
        }

        // Get selected voice, style, personality, and TTS model
        this.selectedVoice = this.voiceSelect.value;
        this.selectedStyle = this.styleSelect.value;
        this.selectedPersonality = this.personalitySelect.value;
        this.selectedTtsModel = this.ttsModelSelect.value;
        console.log('[StreamBuddy] Starting with voice:', this.selectedVoice, 'style:', this.selectedStyle, 'personality:', this.selectedPersonality, 'ttsModel:', this.selectedTtsModel);

        try {
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            console.log('[StreamBuddy] Microphone access granted');
            this.connectWebSocket(script);

            this.setupScreen.classList.add('hidden');
            this.mainScreen.classList.add('active');

        } catch (err) {
            console.error('[StreamBuddy] Failed to start session:', err);
            alert('Failed to access microphone. Please allow microphone access.');
        }
    }

    stopSession() {
        console.log('[StreamBuddy] Stopping session...');

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

        // Pause timer
        this.pauseTimer();

        this.mainScreen.classList.remove('active');
        this.setupScreen.classList.remove('hidden');
        this.setStatus('idle', 'Stopped');
    }

    resetSession() {
        console.log('[StreamBuddy] Resetting session...');

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'reset' }));
        }
        this.transcriptList.innerHTML = '';
        this.buddyText.textContent = 'Listening...';
        this.buddyText.classList.remove('speaking');
        this.buddyPanel.classList.remove('active');
        this.progressFill.style.width = '0%';
        this.sectionInfo.textContent = 'Section 0';
        this.progressPercent.textContent = '0%';

        // Reset sections
        this.currentSection = 0;
        this.completedSections = new Set();
        this.renderSections();

        // Reset timer
        this.resetTimer();
    }

    connectWebSocket(script) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Handle root-path for reverse proxy deployment (e.g., /stream-buddy/)
        const basePath = window.location.pathname.replace(/\/$/, '').replace(/\/index\.html$/, '');
        const wsUrl = `${protocol}//${window.location.host}${basePath}/ws/stream`;

        console.log('[StreamBuddy] Connecting to WebSocket:', wsUrl);

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('[StreamBuddy] WebSocket connected');
            this.isConnected = true;
            this.setStatus('idle', 'Loading script...');
        };

        this.ws.onclose = () => {
            console.log('[StreamBuddy] WebSocket disconnected');
            this.isConnected = false;
        };

        this.ws.onerror = (err) => {
            console.error('[StreamBuddy] WebSocket error:', err);
        };

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            console.log('[StreamBuddy] Received:', msg.type);
            this.handleMessage(msg, script);
        };
    }

    handleMessage(msg, script) {
        switch (msg.type) {
            case 'ready':
                this.sessionId = msg.session_id;
                this.personaName = msg.persona_name;
                console.log(`[StreamBuddy] Session ready: ${this.sessionId}`);
                // Send script, voice, style, personality, and TTS model
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
                console.log('[StreamBuddy] Script loaded', msg.structure);
                // Store and render sections
                this.sections = msg.structure?.sections || [];
                this.currentSection = 0;
                this.completedSections = new Set();
                this.renderSections();
                this.buddyText.textContent = 'Listening...';
                this.setStatus('listening', 'Listening...');
                this.startRecording();
                break;

            case 'transcript':
                console.log('[StreamBuddy] Transcript:', msg.text);
                this.addTranscript('You', msg.text);
                this.setStatus('listening', 'Listening...');
                break;

            case 'show_prompt':
                console.log('[StreamBuddy] Show prompt:', msg.text);
                // Show prompt is now handled by sections list
                break;

            case 'sections_progress':
                console.log('[StreamBuddy] Sections progress:', msg.sections_covered);
                this.updateSectionProgress(msg.sections_covered);
                break;

            case 'cohost_speaking':
                console.log('[StreamBuddy] Co-host preparing:', msg.text);
                this.buddyText.textContent = msg.text;
                this.buddyText.classList.add('speaking');
                this.buddyPanel.classList.add('active');
                this.setStatus('thinking', 'Generating speech...');
                break;

            case 'cohost_audio':
                console.log('[StreamBuddy] Co-host audio received');
                this.addTranscript(this.personaName, msg.text);
                this.setStatus('speaking', 'Speaking...');
                if (msg.audio_base64) {
                    this.playAudio(msg.audio_base64);
                }
                break;

            case 'progress':
                this.updateProgress(msg.section, msg.progress);
                break;

            case 'reset_complete':
                console.log('[StreamBuddy] Reset complete');
                this.setStatus('listening', 'Reset complete');
                break;
        }
    }

    startRecording() {
        if (!this.audioStream || this.isRecording) return;

        console.log('[StreamBuddy] Starting continuous recording...');

        this.mediaRecorder = new MediaRecorder(this.audioStream, {
            mimeType: 'audio/webm;codecs=opus'
        });

        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                // Continuously stream audio to server
                this.ws.send(event.data);
            }
        };

        // Send chunks every 100ms for low latency
        this.mediaRecorder.start(100);
        this.isRecording = true;

        console.log('[StreamBuddy] Recording started (continuous streaming)');
    }

    addTranscript(speaker, text) {
        const li = document.createElement('li');
        li.className = 'transcript-item ' + (speaker === 'You' ? 'user' : 'cohost');
        li.innerHTML = `
            <div class="speaker">${speaker}</div>
            <div class="text">${text}</div>
        `;
        // New transcripts on top
        this.transcriptList.insertBefore(li, this.transcriptList.firstChild);
    }

    updateProgress(section, progress) {
        this.sectionInfo.textContent = `Section ${section}`;
        this.progressPercent.textContent = `${Math.round(progress)}%`;
        this.progressFill.style.width = `${progress}%`;
    }

    renderSections() {
        if (!this.sections.length) {
            this.sectionsList.innerHTML = '<li class="section-item loading">No sections found</li>';
            return;
        }

        this.sectionsList.innerHTML = this.sections.map((section, index) => {
            let stateClass = 'upcoming';
            if (this.completedSections.has(index)) {
                stateClass = 'completed';
            } else if (index === this.currentSection) {
                stateClass = 'current';
            }

            // Get key points (max 2)
            const keyPoints = (section.key_points || []).slice(0, 2);
            const keyPointsHtml = keyPoints.length > 0
                ? `<div class="section-points">${keyPoints.map(p => `<span>• ${p}</span>`).join('')}</div>`
                : '';

            return `
                <li class="section-item ${stateClass}" data-index="${index}">
                    <div class="section-header">
                        <span class="section-number">${index + 1}</span>
                        <span class="section-title">${section.title}</span>
                    </div>
                    ${keyPointsHtml}
                </li>
            `;
        }).join('');

        // Update progress
        const completed = this.completedSections.size;
        const total = this.sections.length;
        const progress = total > 0 ? (completed / total) * 100 : 0;
        this.progressFill.style.width = `${progress}%`;
        this.progressPercent.textContent = `${Math.round(progress)}%`;
        this.sectionInfo.textContent = `Section ${this.currentSection + 1} of ${total}`;
    }

    updateSectionProgress(sectionsCovered) {
        // sectionsCovered is array of section numbers (1-indexed from brain)
        if (!sectionsCovered || !this.sections.length) return;

        sectionsCovered.forEach(sectionNum => {
            // Convert 1-indexed to 0-indexed
            const index = sectionNum - 1;
            if (index >= 0 && index < this.sections.length) {
                this.completedSections.add(index);
            }
        });

        // Update current section to first non-completed
        for (let i = 0; i < this.sections.length; i++) {
            if (!this.completedSections.has(i)) {
                this.currentSection = i;
                break;
            }
        }

        this.renderSections();
    }

    playAudio(base64Audio) {
        console.log('[StreamBuddy] Playing audio...');

        const audio = new Audio('data:audio/mp3;base64,' + base64Audio);
        audio.volume = 0.8;

        this.isPlaying = true;

        audio.onended = () => {
            console.log('[StreamBuddy] Audio playback ended');
            this.isPlaying = false;
            this.setStatus('listening', 'Listening...');
            this.buddyText.classList.remove('speaking');
            this.buddyPanel.classList.remove('active');

            // Tell server we're ready for more audio
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ready_for_audio' }));
            }
        };

        audio.onerror = (e) => {
            console.error('[StreamBuddy] Audio playback error:', e);
            this.isPlaying = false;
            this.setStatus('listening', 'Listening...');
        };

        audio.play().catch(err => {
            console.error('[StreamBuddy] Audio play error:', err);
            this.isPlaying = false;
        });
    }

    setStatus(state, text) {
        this.statusBadge.className = 'status-badge ' + state;
        this.statusBadge.textContent = state.charAt(0).toUpperCase() + state.slice(1);
        this.statusText.textContent = text;

        const icons = {
            idle: '🎙️',
            listening: '👂',
            thinking: '🤔',
            speaking: '🗣️'
        };

        this.statusIcon.textContent = icons[state] || '🎙️';
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
                console.log('[StreamBuddy] Settings loaded from localStorage');
            }
        } catch (e) {
            console.warn('[StreamBuddy] Failed to load settings:', e);
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
            console.log('[StreamBuddy] Settings saved');
        } catch (e) {
            console.warn('[StreamBuddy] Failed to save settings:', e);
        }
    }

    // Timer methods
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

        console.log('[StreamBuddy] Timer started');
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

        console.log('[StreamBuddy] Timer paused at', this.formatTime(this.timerSeconds));
    }

    resetTimer() {
        this.pauseTimer();
        this.timerSeconds = 0;
        this.timerDisplay.textContent = '00:00';
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('[StreamBuddy] DOM loaded, initializing...');
    window.streamBuddy = new StreamBuddy();
});
