/**
 * Stream Buddy OBS Control Panel
 * Plays audio locally, sends lip sync + text to overlay
 */

// VAD Constants
const DEFAULT_PAUSE_DURATION = 1000;
const MAX_SPEECH_DURATION = 30000;
const SILENCE_THRESHOLD = 8;
const VAD_CHECK_INTERVAL = 100;
const BUDDY_TEXT_TTL_MS = 5000;

/**
 * AudioQueue - Plays TTS audio and sends lip sync to overlay
 */
class AudioQueue {
    constructor(app) {
        this.app = app;
        this.queue = [];
        this.isPlaying = false;
        this.clearTextTimeout = null;
    }

    enqueue(audioBase64, text) {
        console.log('[AudioQueue] Enqueuing, queue size:', this.queue.length + 1);
        this.queue.push({ audio: audioBase64, text });
        if (!this.isPlaying) {
            this.playNext();
        }
    }

    playNext() {
        if (this.queue.length === 0) {
            console.log('[AudioQueue] Queue empty, signaling ready');
            this.isPlaying = false;

            // Stop lip sync on overlay
            this.app.sendToOverlay({ type: 'lipsync_end' });

            // Clear text after delay
            if (this.clearTextTimeout) clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = setTimeout(() => {
                this.app.sendToOverlay({ type: 'clear_text' });
                this.clearTextTimeout = null;
            }, BUDDY_TEXT_TTL_MS);

            // Signal server we're ready
            if (this.app.ws && this.app.ws.readyState === WebSocket.OPEN) {
                this.app.ws.send(JSON.stringify({ type: 'ready_for_audio' }));
            }
            this.app.resumeVAD();
            this.app.setStatus('listening', 'Listening...');
            return;
        }

        if (this.clearTextTimeout) {
            clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = null;
        }

        this.isPlaying = true;
        const item = this.queue.shift();
        console.log('[AudioQueue] Playing, remaining:', this.queue.length);

        this.app.playSingleAudio(item.audio, item.text, () => {
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
        this.app.sendToOverlay({ type: 'clear_text' });
        this.app.sendToOverlay({ type: 'lipsync_end' });
    }
}

/**
 * OBS Control Panel App
 */
class OBSPanel {
    constructor() {
        this.ws = null;
        this.avatarWs = null;
        this.isConnected = false;
        this.sessionId = null;
        this.personaName = 'Buddy';

        // Audio recording
        this.mediaRecorder = null;
        this.audioStream = null;
        this.isRecording = false;

        // Audio playback
        this.currentAudio = null;
        this.ttsAudioContext = null;
        this.ttsAnalyser = null;
        this.ttsDataArray = null;
        this.lipSyncInterval = null;

        // Timer
        this.timerSeconds = 0;
        this.timerRunning = false;
        this.timerInterval = null;

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
        this.matchProgress = {};  // {sectionId: {ratio, matched, unmatched, keywords}}

        // Conversation
        this.conversationItems = [];
        this.maxConversationItems = 20;

        // Action parser
        this.actionParser = null;

        // Response mode
        this.autoResponseEnabled = true;
        this.pendingResponseText = null;

        this.init();
    }

    init() {
        // Setup panel elements
        this.setupPanel = document.getElementById('setup-panel');
        this.sessionPanel = document.getElementById('session-panel');
        this.scriptInput = document.getElementById('script-input');
        this.voiceSelect = document.getElementById('voice-select');
        this.styleSelect = document.getElementById('style-select');
        this.proactiveToggle = document.getElementById('proactive-toggle');
        this.predictionCacheToggle = document.getElementById('prediction-cache-toggle');
        this.personalitySelect = document.getElementById('personality-select');
        this.ttsModelSelect = document.getElementById('tts-model-select');
        this.startBtn = document.getElementById('start-btn');
        this.pauseDurationSelect = document.getElementById('pause-duration');
        this.periodicIntervalSelect = document.getElementById('periodic-interval');
        this.autoResponseSelect = document.getElementById('auto-response');

        // Session panel elements
        this.conversationList = document.getElementById('conversation-list');
        this.statusDot = document.getElementById('status-dot');
        this.statusText = document.getElementById('status-text');
        this.sessionIdDisplay = document.getElementById('session-id-display');
        this.progressFill = document.getElementById('progress-fill');
        this.sectionInfo = document.getElementById('section-info');
        this.progressPercent = document.getElementById('progress-percent');
        this.sectionsList = document.getElementById('sections-list');
        this.timerDisplay = document.getElementById('timer-display');
        this.timerBtn = document.getElementById('timer-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.resetBtn = document.getElementById('reset-btn');
        // overlay-url removed - using session-id-copy instead

        // Position controls
        this.posUpBtn = document.getElementById('pos-up');
        this.posDownBtn = document.getElementById('pos-down');
        this.posLeftBtn = document.getElementById('pos-left');
        this.posRightBtn = document.getElementById('pos-right');
        this.posResetBtn = document.getElementById('pos-reset');
        this.zoomInBtn = document.getElementById('zoom-in');
        this.zoomOutBtn = document.getElementById('zoom-out');
        this.zoomNormalBtn = document.getElementById('zoom-normal');

        // Pending response display
        this.pendingResponseEl = document.getElementById('pending-response');
        this.pendingTextEl = document.getElementById('pending-text');

        // Prediction cache panel
        this.predictionCachePanel = document.getElementById('prediction-cache-panel');
        this.cacheStatusEl = document.getElementById('cache-status');
        this.cachedKeywordsList = document.getElementById('cached-keywords-list');
        this.cachedKeywords = [];  // Store keywords with section info
        this.keywordByHotkey = {};  // {1: {keyword, section_id}, 2: {...}, ...} for keyboard trigger

        this.loadSettings();

        // Generate session ID immediately so user can set up OBS
        this.generateSessionId();
        this.updateOverlayUrl();
        this.updateSessionIdCopy();

        // Connect avatar WebSocket early (so OBS overlay works before starting)
        this.connectAvatarWebSocket();

        // Event listeners
        this.startBtn.addEventListener('click', () => this.startSession());
        this.stopBtn.addEventListener('click', () => this.stopSession());
        this.resetBtn.addEventListener('click', () => this.resetSession());
        this.timerBtn.addEventListener('click', () => this.toggleTimer());

        this.posUpBtn.addEventListener('click', () => this.sendToOverlay({ type: 'move', direction: 'up' }));
        this.posDownBtn.addEventListener('click', () => this.sendToOverlay({ type: 'move', direction: 'down' }));
        this.posLeftBtn.addEventListener('click', () => this.sendToOverlay({ type: 'move', direction: 'left' }));
        this.posRightBtn.addEventListener('click', () => this.sendToOverlay({ type: 'move', direction: 'right' }));
        this.posResetBtn.addEventListener('click', () => this.sendToOverlay({ type: 'move_to', x: 960, y: 810 }));
        this.zoomInBtn.addEventListener('click', () => this.sendToOverlay({ type: 'zoom', level: 'in' }));
        this.zoomOutBtn.addEventListener('click', () => this.sendToOverlay({ type: 'zoom', level: 'out' }));
        this.zoomNormalBtn.addEventListener('click', () => this.sendToOverlay({ type: 'zoom', level: 'normal' }));

        [this.voiceSelect, this.styleSelect, this.personalitySelect, this.ttsModelSelect].forEach(el => {
            el.addEventListener('change', () => this.saveSettings());
        });

        // Save all settings on change
        if (this.pauseDurationSelect) {
            this.pauseDurationSelect.addEventListener('change', (e) => {
                this.pauseDuration = parseInt(e.target.value) || DEFAULT_PAUSE_DURATION;
                this.saveSettings();
            });
        }

        if (this.periodicIntervalSelect) {
            this.periodicIntervalSelect.addEventListener('change', (e) => {
                this.periodicInterval = parseInt(e.target.value) || 5;
                this.saveSettings();
            });
        }

        if (this.autoResponseSelect) {
            this.autoResponseSelect.addEventListener('change', (e) => {
                this.autoResponseEnabled = e.target.value === 'true';
                this.saveSettings();
            });
        }

        // Custom voice ID input - show/hide based on voice select
        const customVoiceInput = document.getElementById('custom-voice-id');
        if (customVoiceInput) {
            customVoiceInput.addEventListener('change', () => this.saveSettings());

            // Show/hide custom voice input based on selection
            this.voiceSelect.addEventListener('change', () => {
                customVoiceInput.style.display = this.voiceSelect.value === 'custom' ? 'block' : 'none';
            });

            // Check initial state
            if (this.voiceSelect.value === 'custom') {
                customVoiceInput.style.display = 'block';
            }
        }

        if (typeof ActionParser !== 'undefined') {
            this.actionParser = new ActionParser();
        }

        // Hotkey listener
        document.addEventListener('keydown', (e) => this.handleHotkey(e));

        console.log('[OBSPanel] Initialized');
        console.log('[OBSPanel] Hotkeys: 1-9=cached responses, T=speak, E=complete section, Q=prev, W=recap, P=stop');
    }

    handleHotkey(e) {
        // Skip if typing in an input/textarea
        if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) {
            return;
        }

        // Skip if session not active
        if (!this.isConnected || !this.sessionId) {
            return;
        }

        // Keys 1-9 - Trigger cached keyword response
        if (e.code.startsWith('Digit') && e.code !== 'Digit0') {
            const keyNum = parseInt(e.code.replace('Digit', ''));
            console.log('[OBSPanel] Digit key pressed:', keyNum, 'has mapping:', !!this.keywordByHotkey[keyNum]);
            if (keyNum >= 1 && keyNum <= 9 && this.keywordByHotkey[keyNum]) {
                e.preventDefault();
                this.triggerCachedKeyword(keyNum);
                return;
            }
        }

        // T - Trigger pending response (TTS)
        if (e.code === 'KeyT' && this.pendingResponseText && !this.autoResponseEnabled) {
            e.preventDefault();
            this.triggerPendingResponse();
            return;
        }

        // P - Stop speaking immediately
        if (e.code === 'KeyP') {
            e.preventDefault();
            this.stopSpeaking();
            return;
        }

        // E - Complete current section
        if (e.code === 'KeyE') {
            e.preventDefault();
            this.completeCurrentSection();
            return;
        }

        // Q - Go back to previous section
        if (e.code === 'KeyQ') {
            e.preventDefault();
            this.goToPreviousSection();
            return;
        }

        // W - Recap current section
        if (e.code === 'KeyW') {
            e.preventDefault();
            this.recapCurrentSection();
            return;
        }
    }

    triggerPendingResponse() {
        if (!this.pendingResponseText || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.log('[OBSPanel] No pending response to trigger');
            return;
        }

        console.log('[OBSPanel] Triggering pending response via hotkey');
        this.ws.send(JSON.stringify({ type: 'trigger_response' }));

        this.pendingResponseText = null;
        this.hidePendingResponse();
        this.setStatus('speaking', 'Speaking...');
    }

    showPendingResponse(text, playNotification = true) {
        if (this.pendingResponseEl && this.pendingTextEl) {
            // Strip action tags for display
            let displayText = text;
            if (this.actionParser) {
                displayText = this.actionParser.stripTags(text);
            }
            this.pendingTextEl.textContent = displayText;
            this.pendingResponseEl.classList.add('active');

            // Play notification sound only when audio is ready
            if (playNotification) {
                this.playPendingNotification();
            }
        }
    }

    playPendingNotification() {
        // Create a simple beep using Web Audio API
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            oscillator.frequency.value = 800;  // Hz
            oscillator.type = 'sine';

            gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.2);

            oscillator.start(audioCtx.currentTime);
            oscillator.stop(audioCtx.currentTime + 0.2);

            // Second beep (higher pitch)
            setTimeout(() => {
                const osc2 = audioCtx.createOscillator();
                const gain2 = audioCtx.createGain();
                osc2.connect(gain2);
                gain2.connect(audioCtx.destination);
                osc2.frequency.value = 1000;
                osc2.type = 'sine';
                gain2.gain.setValueAtTime(0.3, audioCtx.currentTime);
                gain2.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.15);
                osc2.start(audioCtx.currentTime);
                osc2.stop(audioCtx.currentTime + 0.15);
            }, 150);
        } catch (e) {
            console.log('[OBSPanel] Could not play notification sound:', e);
        }
    }

    hidePendingResponse() {
        if (this.pendingResponseEl) {
            this.pendingResponseEl.classList.remove('active');
        }
        if (this.pendingTextEl) {
            this.pendingTextEl.textContent = '';
        }
    }

    stopSpeaking() {
        console.log('[OBSPanel] Stop speaking (P key)');

        // Stop current audio
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }

        // Clear audio queue
        this.audioQueue.clear();
        this.stopLipSync();

        // Clear pending response
        this.pendingResponseText = null;
        this.hidePendingResponse();

        // Tell backend to stop
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'stop_speaking' }));
        }

        this.setStatus('listening', 'Stopped speaking');
        this.resumeVAD();
    }

    completeCurrentSection() {
        if (!this.sections.length) return;

        const sectionNum = this.currentSection + 1; // 1-indexed for backend
        console.log('[OBSPanel] Complete section:', sectionNum);

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'complete_section',
                section: sectionNum
            }));
        }

        // Update local state
        this.completedSections.add(this.currentSection);
        if (this.currentSection < this.sections.length - 1) {
            this.currentSection++;
        }
        this.renderSections();
    }

    goToPreviousSection() {
        if (!this.sections.length || this.currentSection === 0) return;

        console.log('[OBSPanel] Go to previous section');

        // Remove current section from completed
        this.completedSections.delete(this.currentSection);
        this.currentSection--;
        // Also remove previous from completed to make it current
        this.completedSections.delete(this.currentSection);

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'go_to_section',
                section: this.currentSection + 1  // 1-indexed
            }));
        }

        this.renderSections();
    }

    recapCurrentSection() {
        if (!this.sections.length) return;

        const section = this.sections[this.currentSection];
        console.log('[OBSPanel] Recap section:', section?.title);

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'recap_section',
                section: this.currentSection + 1  // 1-indexed
            }));
        }
    }

    triggerCachedKeyword(keyNum) {
        const mapping = this.keywordByHotkey[keyNum];
        console.log('[OBSPanel] triggerCachedKeyword called:', keyNum, 'mapping:', mapping, 'all mappings:', this.keywordByHotkey);

        if (!mapping) {
            console.warn('[OBSPanel] No mapping for key', keyNum);
            return;
        }
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('[OBSPanel] WebSocket not connected');
            return;
        }
        if (!mapping.keyword) {
            console.warn('[OBSPanel] Mapping exists but keyword is empty:', mapping);
            return;
        }

        console.log('[OBSPanel] Sending trigger_cached_keyword:', keyNum, '->', mapping.keyword);
        this.ws.send(JSON.stringify({
            type: 'trigger_cached_keyword',
            keyword: mapping.keyword
        }));

        // Visual feedback - highlight the triggered row
        this.setStatus('speaking', `Playing: ${mapping.keyword}`);
        this.highlightTriggeredKeyword(keyNum);
    }

    highlightTriggeredKeyword(keyNum) {
        // Remove previous highlights
        this.cachedKeywordsList?.querySelectorAll('.cached-keyword-row').forEach(el => {
            el.classList.remove('triggered');
        });
        // Add highlight to triggered row
        const row = this.cachedKeywordsList?.querySelector(`[data-key="${keyNum}"]`);
        if (row) row.classList.add('triggered');
    }

    generateSessionId() {
        // Use existing stored ID or create new one (persistent across reloads)
        let storedId = localStorage.getItem('streambuddy_session_id');

        if (storedId) {
            // Reuse existing session ID - OBS URL never needs to change
            this.sessionId = storedId;
            console.log(`[OBSPanel] Reusing session ID: ${this.sessionId}`);
        } else {
            // Generate new ID only if none exists
            const chars = 'abcdef0123456789';
            let id = '';
            for (let i = 0; i < 8; i++) {
                id += chars[Math.floor(Math.random() * chars.length)];
            }
            this.sessionId = id;
            localStorage.setItem('streambuddy_session_id', this.sessionId);
            console.log(`[OBSPanel] Generated new session ID: ${this.sessionId}`);
        }

        // Update display if element exists
        if (this.sessionIdDisplay) {
            this.sessionIdDisplay.textContent = `Session: ${this.sessionId}`;
        }
    }

    updateOverlayUrl() {
        // Now handled by updateSessionIdCopy() - single URL display
        this.updateSessionIdCopy();
    }

    updateSessionIdCopy() {
        const url = `${window.location.protocol}//${window.location.host}/obs/overlay?session=${this.sessionId}`;

        // Update setup panel URL (shown before starting)
        const obsUrlSetup = document.getElementById('obs-url-setup');
        if (obsUrlSetup) {
            obsUrlSetup.textContent = url;
            obsUrlSetup.title = 'Click to copy';
            obsUrlSetup.onclick = () => {
                navigator.clipboard.writeText(url).then(() => {
                    const original = obsUrlSetup.textContent;
                    obsUrlSetup.textContent = '✓ Copied to clipboard!';
                    obsUrlSetup.style.color = '#51cf66';
                    setTimeout(() => {
                        obsUrlSetup.textContent = original;
                        obsUrlSetup.style.color = '#fff';
                    }, 1500);
                });
            };
        }

        // Update session panel URL (shown after starting)
        const sessionIdCopy = document.getElementById('session-id-copy');
        if (sessionIdCopy) {
            sessionIdCopy.textContent = url;
            sessionIdCopy.title = 'Click to copy';
            sessionIdCopy.onclick = () => {
                navigator.clipboard.writeText(url).then(() => {
                    const original = sessionIdCopy.textContent;
                    sessionIdCopy.textContent = '✓ Copied!';
                    sessionIdCopy.style.color = '#51cf66';
                    setTimeout(() => {
                        sessionIdCopy.textContent = original;
                        sessionIdCopy.style.color = '#ffa502';
                    }, 1500);
                });
            };
        }
    }

    // Send message to overlay via avatar WebSocket
    sendToOverlay(msg) {
        if (this.avatarWs && this.avatarWs.readyState === WebSocket.OPEN) {
            this.avatarWs.send(JSON.stringify(msg));
        }
    }

    async startSession() {
        const script = this.scriptInput.value.trim();
        if (!script) {
            alert('Please enter a script first');
            return;
        }

        // Use custom voice ID if selected, otherwise use dropdown value
        const customVoiceInput = document.getElementById('custom-voice-id');
        if (this.voiceSelect.value === 'custom' && customVoiceInput?.value) {
            this.selectedVoice = customVoiceInput.value.trim();
        } else {
            this.selectedVoice = this.voiceSelect.value;
        }
        this.selectedStyle = this.styleSelect.value;
        this.proactiveEnabled = this.proactiveToggle?.checked || false;
        this.predictionCacheEnabled = this.predictionCacheToggle?.checked || false;
        this.selectedPersonality = this.personalitySelect.value;
        this.selectedTtsModel = this.ttsModelSelect.value;
        this.pauseDuration = parseInt(this.pauseDurationSelect?.value) || DEFAULT_PAUSE_DURATION;
        this.periodicInterval = parseInt(this.periodicIntervalSelect?.value) || 5;
        this.autoResponseEnabled = this.autoResponseSelect?.value !== 'false';

        try {
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
            });

            console.log('[OBSPanel] Microphone access granted');
            this.connectWebSocket(script);

            this.setupPanel.classList.add('hidden');
            this.sessionPanel.classList.add('active');

            this.conversationItems = [];
            this.renderConversation();

        } catch (err) {
            console.error('[OBSPanel] Failed to start session:', err);
            alert('Failed to access microphone.');
        }
    }

    stopSession() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
        }
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }
        if (this.ws) { this.ws.close(); this.ws = null; }
        if (this.avatarWs) { this.avatarWs.close(); this.avatarWs = null; }

        this.stopLipSync();
        this.audioQueue.clear();
        this.pauseTimer();
        this.hidePredictionCachePanel();

        this.setupPanel.classList.remove('hidden');
        this.sessionPanel.classList.remove('active');
        this.setStatus('idle', 'Stopped');
    }

    resetSession() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'reset' }));
        }

        this.audioQueue.clear();
        this.conversationItems = [];
        this.renderConversation();
        this.progressFill.style.width = '0%';
        this.sectionInfo.textContent = 'Section 0';
        this.progressPercent.textContent = '0%';

        this.currentSection = 0;
        this.completedSections = new Set();
        this.renderSections();
        this.resetTimer();

        // Reset prediction cache panel
        this.hidePredictionCachePanel();
    }

    hidePredictionCachePanel() {
        if (this.predictionCachePanel) {
            this.predictionCachePanel.style.display = 'none';
        }
        this.cachedKeywords = [];
        this.keywordByHotkey = {};
    }

    connectWebSocket(script) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Pass session ID to server so it uses our pre-generated ID
        const wsUrl = `${protocol}//${window.location.host}/ws/stream?session=${this.sessionId}`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.isConnected = true;
            this.setStatus('connected', 'Loading script...');
        };

        this.ws.onclose = () => {
            this.isConnected = false;
            this.setStatus('disconnected', 'Disconnected');
        };

        this.ws.onerror = (err) => console.error('[OBSPanel] WebSocket error:', err);

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            this.handleMessage(msg, script);
        };
    }

    connectAvatarWebSocket() {
        if (!this.sessionId) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/avatar/${this.sessionId}`;

        this.avatarWs = new WebSocket(url);
        this.avatarWs.onopen = () => console.log('[OBSPanel] Avatar WebSocket connected');
        this.avatarWs.onclose = () => console.log('[OBSPanel] Avatar WebSocket disconnected');
        this.avatarWs.onerror = (err) => console.error('[OBSPanel] Avatar WebSocket error:', err);
    }

    handleMessage(msg, script) {
        switch (msg.type) {
            case 'ready':
                // Server confirms session - use server's ID if different (shouldn't be)
                if (msg.session_id && msg.session_id !== this.sessionId) {
                    console.log(`[OBSPanel] Session ID mismatch: client=${this.sessionId}, server=${msg.session_id}`);
                }
                this.personaName = msg.persona_name;
                this.sessionIdDisplay.textContent = `Session: ${this.sessionId}`;

                // Avatar WS already connected on page load, no need to reconnect

                this.ws.send(JSON.stringify({
                    type: 'load_script',
                    script: script,
                    voice: this.selectedVoice,
                    style: this.selectedStyle,
                    proactive: this.proactiveEnabled,
                    personality: this.selectedPersonality,
                    tts_model: this.selectedTtsModel,
                    use_prediction_cache: this.predictionCacheEnabled
                }));
                break;

            case 'script_loaded':
                this.sections = msg.structure?.sections || [];
                this.currentSection = 0;
                this.completedSections = new Set();
                this.renderSections();
                // Don't start recording yet - wait for user to click "Start"
                this.setStatus('connected', 'Ready - click Start to begin');

                this.ws.send(JSON.stringify({ type: 'set_auto_response', enabled: this.autoResponseEnabled }));
                this.ws.send(JSON.stringify({ type: 'set_periodic_interval', seconds: this.periodicInterval }));
                break;

            case 'response_pending':
                // Manual mode - processing TTS in background
                // Don't show text yet - wait until audio is ready
                console.log('[OBSPanel] Response pending (processing TTS):', msg.text?.substring(0, 50));
                this.pendingResponseText = msg.text;
                this.setStatus('pending', 'Processing TTS...');
                // Don't call showPendingResponse here - text will show when audio_ready is received
                break;

            case 'audio_ready':
                // Manual mode - audio is ready, can press T now
                console.log('[OBSPanel] Audio ready (press T):', msg.text?.substring(0, 50));
                this.pendingResponseText = msg.text;
                this.setStatus('pending', 'Audio ready (T to speak)');
                this.showPendingResponse(msg.text, true);  // Play ding now
                break;

            case 'transcript':
                if (msg.text && msg.text.trim()) {
                    this.addConversationItem('user', msg.text.trim());
                }
                // Don't reset status if there's a pending response waiting
                if (!this.pendingResponseText) {
                    this.setStatus('listening', 'Listening...');
                }
                break;

            case 'sections_progress':
                this.updateSectionProgress(msg.sections_covered);
                break;

            case 'keyword_progress':
                // Update keyword match progress
                if (msg.match_progress) {
                    this.matchProgress = msg.match_progress;
                }
                if (msg.sections_covered) {
                    this.updateSectionProgress(msg.sections_covered);
                }
                this.updateKeywordHighlights();
                break;

            case 'cohost_speaking':
                this.setStatus('speaking', 'Speaking...');
                this.hidePendingResponse();
                this.pauseVAD();
                break;

            case 'cohost_audio':
            case 'cohost_audio_queued':
                this.pauseVAD();
                this.setStatus('speaking', 'Speaking...');

                let displayText = msg.text;
                if (this.actionParser) {
                    const parsed = this.actionParser.parseWithTiming(msg.text, 60);
                    displayText = parsed.cleanText;
                }

                if (displayText && displayText.trim()) {
                    this.addConversationItem('buddy', displayText.trim());
                }

                // Queue audio for playback
                this.audioQueue.enqueue(msg.audio_base64, displayText);
                break;

            case 'progress':
                this.updateProgress(msg.section, msg.progress);
                break;

            case 'reset_complete':
                this.setStatus('listening', 'Reset complete');
                break;

            case 'show_prompt':
                // Display recap or prompt text
                console.log('[OBSPanel] Show prompt:', msg.text?.substring(0, 50));
                this.addConversationItem('system', msg.text || '');
                break;

            case 'stop_speaking_ack':
                console.log('[OBSPanel] Stop speaking acknowledged');
                break;

            case 'prediction_status':
                // Prediction cache generation status
                console.log('[OBSPanel] Prediction cache:', msg.status, msg.cached_count || '');
                this.showPredictionCachePanel(msg);
                break;

            case 'prediction_hit':
                // Cache hit - instant response was sent
                console.log('[OBSPanel] Prediction hit:', msg.keyword);
                this.highlightCacheHit(msg.keyword);
                this.addConversationItem('system', `⚡ Cache hit: "${msg.keyword}"`);
                break;

        }
    }


    // Play audio and send lip sync to overlay
    playSingleAudio(audioBase64, text, onComplete) {
        console.log('[OBSPanel] Playing audio:', text?.substring(0, 40));

        // Send text to overlay for display
        this.sendToOverlay({ type: 'display_text', text: text });

        // Create audio element
        this.currentAudio = new Audio('data:audio/mp3;base64,' + audioBase64);
        this.currentAudio.volume = 0.8;

        // Setup audio context once
        if (!this.ttsAudioContext) {
            this.ttsAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.ttsAnalyser = this.ttsAudioContext.createAnalyser();
            this.ttsAnalyser.fftSize = 256;
            this.ttsAnalyser.smoothingTimeConstant = 0.5;
            this.ttsDataArray = new Uint8Array(this.ttsAnalyser.frequencyBinCount);
            // Connect analyser to destination ONCE
            this.ttsAnalyser.connect(this.ttsAudioContext.destination);
            this.ttsAnalyserConnected = true;
            console.log('[OBSPanel] Audio context created for lip sync');
        }

        // Connect this audio element to the analyser
        try {
            const source = this.ttsAudioContext.createMediaElementSource(this.currentAudio);
            source.connect(this.ttsAnalyser);
            console.log('[OBSPanel] Audio connected to analyser');
        } catch (e) {
            console.error('[OBSPanel] Failed to connect audio to analyser:', e);
        }

        if (this.ttsAudioContext.state === 'suspended') {
            this.ttsAudioContext.resume();
        }

        // Start lip sync forwarding
        this.startLipSync();

        this.currentAudio.onended = () => {
            console.log('[OBSPanel] Audio ended');
            this.stopLipSync();
            if (onComplete) onComplete();
        };

        this.currentAudio.onerror = (e) => {
            console.error('[OBSPanel] Audio error:', e);
            this.stopLipSync();
            if (onComplete) onComplete();
        };

        this.currentAudio.play().catch(e => {
            console.error('[OBSPanel] Audio play failed:', e);
            this.stopLipSync();
            if (onComplete) onComplete();
        });
    }

    startLipSync() {
        if (this.lipSyncInterval) return;

        console.log('[OBSPanel] Starting lip sync, avatarWs connected:', this.avatarWs?.readyState === WebSocket.OPEN);

        // Notify overlay that speech is starting
        this.sendToOverlay({ type: 'lipsync_start' });

        let sampleCount = 0;
        this.lipSyncInterval = setInterval(() => {
            if (!this.ttsAnalyser || !this.ttsDataArray) return;

            this.ttsAnalyser.getByteFrequencyData(this.ttsDataArray);

            // Calculate amplitude (focus on voice frequencies 100-3000Hz)
            let sum = 0;
            const start = Math.floor(100 / (this.ttsAudioContext.sampleRate / this.ttsAnalyser.fftSize));
            const end = Math.floor(3000 / (this.ttsAudioContext.sampleRate / this.ttsAnalyser.fftSize));
            for (let i = start; i < end && i < this.ttsDataArray.length; i++) {
                sum += this.ttsDataArray[i];
            }
            const amplitude = sum / (end - start) / 255;

            // Send to overlay
            this.sendToOverlay({ type: 'lipsync', amplitude: amplitude });

            // Log every 10th sample for debugging
            sampleCount++;
            if (sampleCount % 10 === 0) {
                console.log(`[OBSPanel] Lip sync amplitude: ${amplitude.toFixed(3)}`);
            }
        }, 50); // 20fps lip sync updates
    }

    stopLipSync() {
        if (this.lipSyncInterval) {
            clearInterval(this.lipSyncInterval);
            this.lipSyncInterval = null;
        }
        this.sendToOverlay({ type: 'lipsync', amplitude: 0 });
    }

    // Recording & VAD
    startRecording() {
        if (!this.audioStream || this.isRecording) return;

        this.mediaRecorder = new MediaRecorder(this.audioStream, { mimeType: 'audio/webm;codecs=opus' });
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(event.data);
            }
        };

        this.mediaRecorder.start(100);
        this.isRecording = true;
        this.startVAD();
    }

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
            if (this.speechStartTime === 0) this.speechStartTime = now;
            this.lastSpeechTime = now;

            if (now - this.speechStartTime >= MAX_SPEECH_DURATION) {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'transcribe_now' }));
                }
                this.speechStartTime = now;
            }
        } else {
            if (now - this.lastSpeechTime >= this.pauseDuration && this.lastSpeechTime > 0 && this.speechStartTime > 0) {
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
        if (this.vadInterval) { clearInterval(this.vadInterval); this.vadInterval = null; }
    }

    resumeVAD() {
        if (!this.vadInterval) return;
        this.vadEnabled = true;
        this.lastSpeechTime = Date.now();
        this.speechStartTime = 0;
    }

    pauseVAD() { this.vadEnabled = false; }

    // UI
    setStatus(state, text) {
        this.statusDot.className = 'status-dot';
        if (state === 'connected' || state === 'listening') this.statusDot.classList.add('connected');
        else if (state === 'speaking') this.statusDot.classList.add('speaking');
        else if (state === 'pending') this.statusDot.classList.add('pending');
        this.statusText.textContent = text;
    }

    updateProgress(section, progress) {
        this.sectionInfo.textContent = `Section ${section}`;
        this.progressPercent.textContent = `${Math.round(progress)}%`;
        this.progressFill.style.width = `${progress}%`;
    }

    addConversationItem(speaker, text) {
        // Skip duplicates (same speaker + same text within last 3 items)
        const recentItems = this.conversationItems.slice(-3);
        const isDuplicate = recentItems.some(item =>
            item.speaker === speaker && item.text === text
        );
        if (isDuplicate) {
            console.log('[OBSPanel] Skipping duplicate:', text.substring(0, 30));
            return;
        }

        this.conversationItems.push({ speaker, text, timestamp: Date.now() });
        if (this.conversationItems.length > this.maxConversationItems) this.conversationItems.shift();
        this.renderConversation();
    }

    renderConversation() {
        if (!this.conversationList) return;
        this.conversationList.innerHTML = this.conversationItems.map((item, i) => {
            const isLast = i === this.conversationItems.length - 1;
            const speakingClass = (isLast && item.speaker === 'buddy') ? ' speaking' : '';
            let label = 'System';
            if (item.speaker === 'user') label = 'You';
            else if (item.speaker === 'buddy') label = this.personaName;
            return `<div class="conversation-item ${item.speaker}${speakingClass}">
                <div class="speaker">${label}</div>
                <div class="text">${this.escapeHtml(item.text)}</div>
            </div>`;
        }).join('');
        this.conversationList.scrollTop = this.conversationList.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    renderSections() {
        if (!this.sections.length) {
            this.sectionsList.innerHTML = '<li class="section-item">No sections</li>';
            return;
        }

        this.sectionsList.innerHTML = this.sections.map((section, i) => {
            const sectionId = section.id || (i + 1);
            let stateClass = this.completedSections.has(i) ? 'completed' : (i === this.currentSection ? 'current' : 'upcoming');

            // Filter out action-type key_points (only show speech type)
            const keyPoints = (section.key_points || []).filter(p => {
                if (typeof p === 'object') {
                    return p.type !== 'action';
                }
                return true;
            });
            let pointsHtml = keyPoints.length ? `<div class="section-points">${keyPoints.map(p => {
                const text = typeof p === 'string' ? p : (p.text || '');
                return `<span>${this.escapeHtml(text)}</span>`;
            }).join('')}</div>` : '';

            // Show section keywords with match highlighting
            // Handle both array and string (in case LLM returns wrong format)
            let keywords = section.section_keywords || [];
            if (typeof keywords === 'string') {
                keywords = keywords.split(/[,\s]+/).filter(k => k.length > 0);
            }
            const keywordsHtml = keywords.length > 0
                ? `<div class="section-keywords" data-section-id="${sectionId}">
                    <span class="keywords-label">Keywords:</span>
                    ${keywords.map(k => `<span class="keyword" data-keyword="${this.escapeHtml(k)}">${this.escapeHtml(k)}</span>`).join('')}
                   </div>`
                : '';

            // Keyword match progress bar
            const progressHtml = `<div class="keyword-progress-bar" data-section-id="${sectionId}">
                <div class="keyword-progress-fill" style="width: 0%"></div>
                <span class="keyword-progress-text">0%</span>
            </div>`;

            return `<li class="section-item ${stateClass}" data-section-id="${sectionId}">
                <div class="section-header">
                    <span class="section-number">${i + 1}</span>
                    <span class="section-title">${this.escapeHtml(section.title)}</span>
                </div>${pointsHtml}${keywordsHtml}${progressHtml}
            </li>`;
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
        sectionsCovered.forEach(num => {
            const idx = num - 1;
            if (idx >= 0 && idx < this.sections.length) this.completedSections.add(idx);
        });
        for (let i = 0; i < this.sections.length; i++) {
            if (!this.completedSections.has(i)) { this.currentSection = i; break; }
        }
        this.renderSections();
        this.updateKeywordHighlights();
    }

    updateKeywordHighlights() {
        // Update keyword highlights based on matchProgress
        for (const [sectionId, progress] of Object.entries(this.matchProgress)) {
            const container = this.sectionsList.querySelector(`.section-keywords[data-section-id="${sectionId}"]`);
            if (!container) continue;

            // Highlight matched keywords
            const matched = new Set((progress.matched || []).map(k => k.toLowerCase()));
            container.querySelectorAll('.keyword').forEach(keywordEl => {
                const keyword = keywordEl.dataset.keyword.toLowerCase();
                if (matched.has(keyword)) {
                    keywordEl.classList.add('matched');
                } else {
                    keywordEl.classList.remove('matched');
                }
            });

            // Update progress bar
            const progressBar = this.sectionsList.querySelector(`.keyword-progress-bar[data-section-id="${sectionId}"]`);
            if (progressBar) {
                const ratio = progress.ratio || 0;
                const fill = progressBar.querySelector('.keyword-progress-fill');
                const text = progressBar.querySelector('.keyword-progress-text');
                if (fill) fill.style.width = `${ratio}%`;
                if (text) text.textContent = `${ratio}%`;

                // Color based on progress
                if (progress.complete) {
                    progressBar.classList.add('complete');
                    progressBar.classList.remove('good');
                } else if (ratio >= 50) {
                    progressBar.classList.add('good');
                    progressBar.classList.remove('complete');
                } else {
                    progressBar.classList.remove('good', 'complete');
                }
            }
        }
    }

    // Prediction Cache UI
    showPredictionCachePanel(msg) {
        if (!this.predictionCachePanel) {
            console.warn('[OBSPanel] Prediction cache panel not found');
            return;
        }

        console.log('[OBSPanel] showPredictionCachePanel:', msg);

        const loadingBar = document.getElementById('cache-loading-bar');
        const loadingProgress = document.getElementById('cache-loading-progress');
        const loadingText = document.getElementById('cache-loading-text');

        if (msg.status === 'generating') {
            this.predictionCachePanel.style.display = 'block';
            this.cacheStatusEl.textContent = 'Generating...';
            this.cacheStatusEl.className = 'cache-status generating';
            this.cachedKeywordsList.innerHTML = '';

            // Show loading bar with indeterminate animation
            if (loadingBar) {
                loadingBar.style.display = 'block';
                loadingProgress.className = 'loading-progress indeterminate';
                loadingText.textContent = msg.message || 'Preloading welcome speech & keywords...';
            }
        } else if (msg.status === 'ready') {
            this.predictionCachePanel.style.display = 'block';
            this.cacheStatusEl.textContent = `${msg.cached_count || 0} keywords ready`;
            this.cacheStatusEl.className = 'cache-status ready';

            // Hide loading bar
            if (loadingBar) {
                loadingProgress.className = 'loading-progress';
                loadingProgress.style.width = '100%';
                loadingText.textContent = 'Ready!';
                setTimeout(() => {
                    loadingBar.style.display = 'none';
                }, 500);
            }

            // Store and render keywords
            this.cachedKeywords = msg.keywords || [];
            console.log('[OBSPanel] Cached keywords received:', JSON.stringify(this.cachedKeywords));

            if (this.cachedKeywords.length > 0) {
                this.renderCachedKeywords();
                console.log('[OBSPanel] After renderCachedKeywords, keywordByHotkey:', JSON.stringify(this.keywordByHotkey));
            } else {
                this.cachedKeywordsList.innerHTML = '<span style="color: #888; font-size: 0.8rem;">No keywords generated</span>';
            }
        } else if (msg.status === 'error') {
            this.predictionCachePanel.style.display = 'block';
            this.cacheStatusEl.textContent = 'Error';
            this.cacheStatusEl.className = 'cache-status';

            // Hide loading bar on error
            if (loadingBar) {
                loadingBar.style.display = 'none';
            }

            this.cachedKeywordsList.innerHTML = `<span style="color: #ff6b6b; font-size: 0.8rem;">${msg.message || 'Unknown error'}</span>`;
        }
    }

    renderCachedKeywords() {
        if (!this.cachedKeywordsList || !this.cachedKeywords.length) return;

        // Sort by section_id to get consistent key ordering
        const sorted = [...this.cachedKeywords].sort((a, b) => {
            const aSection = typeof a === 'object' ? (a.section_id || 0) : 0;
            const bSection = typeof b === 'object' ? (b.section_id || 0) : 0;
            return aSection - bSection;
        });

        // Clear and rebuild hotkey mapping
        this.keywordByHotkey = {};

        this.cachedKeywordsList.innerHTML = sorted.map((item, index) => {
            const keyword = typeof item === 'string' ? item : (item.keyword || '');
            const response = typeof item === 'object' ? (item.response || '') : '';
            const sectionId = typeof item === 'object' ? (item.section_id || 0) : 0;
            const sectionLabel = typeof item === 'object' ? (item.section_label || '') : '';
            const sectionTitle = typeof item === 'object' ? (item.section_title || '') : '';
            const keyNum = index + 1;  // Keys 1-9

            console.log(`[OBSPanel] Processing keyword ${keyNum}:`, keyword, 'from item:', item);

            // Store mapping for hotkey lookup (only if keyword is valid)
            if (keyNum <= 9 && keyword) {
                this.keywordByHotkey[keyNum] = {
                    keyword: keyword,
                    section_id: sectionId
                };
            }

            const tooltipAttr = response ? `title="${this.escapeHtml(response)}"` : '';

            // Section label badge color
            const labelColor = sectionLabel === 'Intro' ? '#4ecdc4' : sectionLabel === 'Ending' ? '#ff6b6b' : '#a78bfa';
            const labelBadge = sectionLabel ? `<span class="section-label-badge" style="background:${labelColor};color:#fff;font-size:0.6rem;padding:1px 4px;border-radius:3px;margin-right:4px;">${this.escapeHtml(sectionLabel)}</span>` : '';
            const titleText = sectionTitle ? `<span class="section-title-text" style="color:#888;font-size:0.7rem;margin-left:4px;">${this.escapeHtml(sectionTitle)}</span>` : '';

            return `<div class="cached-keyword-row ready" data-key="${keyNum}" data-keyword="${this.escapeHtml((keyword || '').toLowerCase())}">
                <span class="hotkey-badge">${keyNum <= 9 ? keyNum : '-'}</span>
                ${labelBadge}<span class="keyword-text" ${tooltipAttr}>${this.escapeHtml(keyword || '(empty)')}</span>
                ${titleText}
                <span class="status-icon">✓</span>
            </div>`;
        }).join('');

        console.log('[OBSPanel] Hotkey mapping:', this.keywordByHotkey);
    }

    highlightCacheHit(keyword) {
        if (!this.cachedKeywordsList) return;

        const normalizedKeyword = keyword.toLowerCase();
        const row = this.cachedKeywordsList.querySelector(`[data-keyword="${normalizedKeyword}"]`);
        if (row) {
            row.classList.add('triggered');
            // Remove triggered class after animation
            setTimeout(() => row.classList.remove('triggered'), 2000);
        }
    }

    // Timer
    formatTime(s) { return `${Math.floor(s/60).toString().padStart(2,'0')}:${(s%60).toString().padStart(2,'0')}`; }
    toggleTimer() { this.timerRunning ? this.pauseTimer() : this.startTimer(); }

    startTimer() {
        this.timerRunning = true;
        this.timerBtn.textContent = 'Pause';
        this.timerBtn.classList.replace('start', 'pause');
        this.timerDisplay.classList.add('running');
        this.timerInterval = setInterval(() => {
            this.timerSeconds++;
            this.timerDisplay.textContent = this.formatTime(this.timerSeconds);
        }, 1000);

        // Start recording/STT now (not on script_loaded)
        this.startRecording();
        this.setStatus('listening', this.autoResponseEnabled ? 'Listening...' : 'Listening (T to speak)...');

        // Send start_presentation to server - triggers welcome message (especially for proactive mode)
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log('[OBSPanel] Sending start_presentation to server');
            this.ws.send(JSON.stringify({ type: 'start_presentation' }));
        }
    }

    pauseTimer() {
        this.timerRunning = false;
        this.timerBtn.textContent = 'Start';
        this.timerBtn.classList.replace('pause', 'start');
        this.timerDisplay.classList.remove('running');
        if (this.timerInterval) { clearInterval(this.timerInterval); this.timerInterval = null; }
    }

    resetTimer() { this.pauseTimer(); this.timerSeconds = 0; this.timerDisplay.textContent = '00:00'; }

    // Settings
    loadSettings() {
        try {
            const saved = localStorage.getItem('streambuddy_settings');
            if (saved) {
                const s = JSON.parse(saved);
                if (s.voice) this.voiceSelect.value = s.voice;
                if (s.style) this.styleSelect.value = s.style;
                if (s.personality) this.personalitySelect.value = s.personality;
                if (s.ttsModel) this.ttsModelSelect.value = s.ttsModel;
                if (s.periodicInterval && this.periodicIntervalSelect) {
                    this.periodicIntervalSelect.value = s.periodicInterval;
                    this.periodicInterval = parseInt(s.periodicInterval) || 5;
                }
                if (s.pauseDuration && this.pauseDurationSelect) {
                    this.pauseDurationSelect.value = s.pauseDuration;
                    this.pauseDuration = parseInt(s.pauseDuration) || DEFAULT_PAUSE_DURATION;
                }
                if (s.autoResponse !== undefined && this.autoResponseSelect) {
                    this.autoResponseSelect.value = s.autoResponse;
                    this.autoResponseEnabled = s.autoResponse === 'true';
                }
                if (s.customVoiceId) {
                    const customVoiceInput = document.getElementById('custom-voice-id');
                    if (customVoiceInput) {
                        customVoiceInput.value = s.customVoiceId;
                        // If there's a custom voice ID, select "custom" and show the input
                        if (s.voice === 'custom') {
                            customVoiceInput.style.display = 'block';
                        }
                    }
                }
                if (s.proactive !== undefined && this.proactiveToggle) {
                    this.proactiveToggle.checked = s.proactive;
                }
                if (s.predictionCache !== undefined && this.predictionCacheToggle) {
                    this.predictionCacheToggle.checked = s.predictionCache;
                }
            }
        } catch (e) {}
    }

    saveSettings() {
        try {
            const customVoiceInput = document.getElementById('custom-voice-id');
            localStorage.setItem('streambuddy_settings', JSON.stringify({
                voice: this.voiceSelect.value,
                style: this.styleSelect.value,
                proactive: this.proactiveToggle?.checked || false,
                predictionCache: this.predictionCacheToggle?.checked || false,
                personality: this.personalitySelect.value,
                ttsModel: this.ttsModelSelect.value,
                periodicInterval: this.periodicIntervalSelect?.value || '5',
                pauseDuration: this.pauseDurationSelect?.value || '2000',
                autoResponse: this.autoResponseSelect?.value || 'true',
                customVoiceId: customVoiceInput?.value || ''
            }));
        } catch (e) {}
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.obsPanel = new OBSPanel();
});
