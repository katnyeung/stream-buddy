/**
 * Stream Buddy - Frontend Application
 * Continuous streaming with VAD-triggered transcription
 */

// VAD Constants
const DEFAULT_PAUSE_DURATION = 2000;             // Default 2s pause → transcribe_now
const MAX_SPEECH_DURATION = 30000;               // 30s max speaking → transcribe_now
const SILENCE_THRESHOLD = 8;                     // RMS threshold
const VAD_CHECK_INTERVAL = 100;                  // Check every 100ms

// TTS Display TTL (how long to show buddy text after speaking)
const BUDDY_TEXT_TTL_MS = 5000;                  // 5 seconds

/**
 * AudioQueue - Manages TTS playback queue
 * Plays audio chunks sequentially, signals when done
 */
class AudioQueue {
    constructor(app) {
        this.app = app;
        this.queue = [];
        this.isPlaying = false;
        this.clearTextTimeout = null;  // TTL timeout for buddy text
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

            // Clear buddy text after TTL delay
            if (this.clearTextTimeout) {
                clearTimeout(this.clearTextTimeout);
            }
            this.clearTextTimeout = setTimeout(() => {
                this.app.buddyText.innerHTML = '';
                this.app.buddyText.classList.remove('speaking');
                this.app.buddySection.classList.remove('active');
                this.clearTextTimeout = null;
            }, BUDDY_TEXT_TTL_MS);

            // Signal server we're ready for more
            if (this.app.ws && this.app.ws.readyState === WebSocket.OPEN) {
                this.app.ws.send(JSON.stringify({ type: 'ready_for_audio' }));
            }
            // Resume VAD
            this.app.resumeVAD();
            return;
        }

        // Cancel any pending clear if we have more to play
        if (this.clearTextTimeout) {
            clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = null;
        }

        this.isPlaying = true;
        const item = this.queue.shift();
        console.log('[AudioQueue] Playing next item, remaining:', this.queue.length);

        // Play with callback to chain to next
        this.app.playSingleAudio(item.audio, item.text, item.actions, () => {
            this.playNext();
        });
    }

    clear() {
        console.log('[AudioQueue] Clearing queue');
        this.queue = [];
        this.isPlaying = false;

        // Cancel any pending TTL clear
        if (this.clearTextTimeout) {
            clearTimeout(this.clearTextTimeout);
            this.clearTextTimeout = null;
        }

        // Clear buddy text display immediately on explicit clear
        this.app.buddyText.innerHTML = '';
        this.app.buddyText.classList.remove('speaking');
        this.app.buddySection.classList.remove('active');
    }

    get length() {
        return this.queue.length;
    }
}

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
        this.currentAudioElement = null;

        // Scheduled action timeouts (for cancellation)
        this.scheduledActionTimeouts = [];

        // Timer
        this.timerSeconds = 0;
        this.timerRunning = false;
        this.timerInterval = null;

        // Avatar
        this.avatarManager = null;
        this.avatarEnabled = false;

        // Action system (LLM command tags)
        this.actionParser = null;
        this.actionLibrary = null;
        this.actionExecutor = null;

        // Pending actions to schedule when audio plays
        this.pendingActions = null;

        // VAD (Voice Activity Detection)
        this.vadInterval = null;
        this.lastSpeechTime = 0;
        this.speechStartTime = 0;  // Track when continuous speech started
        this.vadEnabled = false;
        this.inputAnalyser = null;
        this.inputAudioContext = null;
        this.lastListeningGesture = 0;  // Track listening animations
        this.pauseDuration = DEFAULT_PAUSE_DURATION;  // Configurable pause duration

        // Audio Queue for TTS playback
        this.audioQueue = new AudioQueue(this);

        // Manual response mode
        this.autoResponseEnabled = true;
        this.pendingResponseText = null;  // Store pending response for manual trigger
        this.periodicInterval = 5;  // Periodic transcription interval in seconds

        this.init();
    }

    init() {
        // Setup screen elements
        this.setupScreen = document.getElementById('setup-screen');
        this.mainScreen = document.getElementById('main-screen');
        this.scriptInput = document.getElementById('script-input');
        this.voiceSelect = document.getElementById('voice-select');
        this.styleSelect = document.getElementById('style-select');
        this.proactiveToggle = document.getElementById('proactive-toggle');
        this.personalitySelect = document.getElementById('personality-select');
        this.ttsModelSelect = document.getElementById('tts-model-select');
        this.startBtn = document.getElementById('start-btn');

        // Load saved settings from localStorage
        this.loadSettings();

        // Save settings on change
        this.voiceSelect.addEventListener('change', () => this.saveSettings());
        this.styleSelect.addEventListener('change', () => this.saveSettings());
        if (this.proactiveToggle) this.proactiveToggle.addEventListener('change', () => this.saveSettings());
        this.personalitySelect.addEventListener('change', () => this.saveSettings());
        this.ttsModelSelect.addEventListener('change', () => this.saveSettings());

        // Main screen elements
        this.sectionsList = document.getElementById('sections-list');
        this.buddyText = document.getElementById('buddy-text');
        this.buddySection = document.querySelector('.buddy-section');
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

        // Manual response mode elements
        this.autoResponseCheckbox = document.getElementById('auto-response');
        this.autoResponseLabel = document.getElementById('auto-response-label');
        this.periodicIntervalSelect = document.getElementById('periodic-interval');

        // Event listeners
        this.startBtn.addEventListener('click', () => this.startSession());
        this.stopBtn.addEventListener('click', () => this.stopSession());
        this.resetBtn.addEventListener('click', () => this.resetSession());
        this.timerBtn.addEventListener('click', () => this.toggleTimer());

        // Auto/Manual response toggle
        if (this.autoResponseCheckbox) {
            this.autoResponseCheckbox.addEventListener('change', (e) => {
                this.autoResponseEnabled = e.target.checked;
                this.updateAutoResponseUI();
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'set_auto_response',
                        enabled: this.autoResponseEnabled
                    }));
                }
            });
        }

        // Periodic interval selector
        if (this.periodicIntervalSelect) {
            this.periodicIntervalSelect.addEventListener('change', (e) => {
                this.periodicInterval = parseInt(e.target.value) || 0;
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'set_periodic_interval',
                        seconds: this.periodicInterval
                    }));
                }
            });
        }

        // Pause duration selector
        this.pauseDurationSelect = document.getElementById('pause-duration');
        if (this.pauseDurationSelect) {
            this.pauseDurationSelect.addEventListener('change', (e) => {
                this.pauseDuration = parseInt(e.target.value) || DEFAULT_PAUSE_DURATION;
                console.log('[VAD] Pause duration:', this.pauseDuration + 'ms');
            });
        }

        // Hotkey listener for manual response trigger (Space key) and section controls
        document.addEventListener('keydown', (e) => {
            // Skip if typing in an input/textarea
            if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) {
                return;
            }

            // Space - Trigger pending response (TTS)
            if (e.code === 'Space' &&
                this.pendingResponseText &&
                !this.autoResponseEnabled) {
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
        });

        console.log('[StreamBuddy] Initialized');
        console.log('[StreamBuddy] Hotkeys: Space=speak, E=complete section, Q=prev section, W=recap, P=stop');

        // Initialize avatar (async)
        this.initAvatar();
    }

    updateAutoResponseUI() {
        if (this.autoResponseLabel) {
            this.autoResponseLabel.textContent = this.autoResponseEnabled
                ? 'Auto (avatar speaks automatically)'
                : 'Manual (press Space to speak)';
        }
    }

    triggerPendingResponse() {
        if (!this.pendingResponseText || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.log('[StreamBuddy] No pending response to trigger');
            return;
        }

        console.log('[StreamBuddy] Triggering pending response via hotkey');
        this.ws.send(JSON.stringify({ type: 'trigger_response' }));

        // Clear pending state
        this.pendingResponseText = null;
        this.buddySection.classList.remove('pending');
    }

    stopSpeaking() {
        console.log('[StreamBuddy] Stop speaking (P key)');

        // Stop current audio
        if (this.currentAudioElement) {
            this.currentAudioElement.pause();
            this.currentAudioElement.currentTime = 0;
            this.currentAudioElement = null;
        }

        // Clear audio queue
        this.audioQueue.clear();

        // Cancel scheduled actions
        this.cancelScheduledActions();

        // Tell backend to stop
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'stop_speaking' }));
        }

        this.isPlaying = false;
        this.setStatus('listening', 'Stopped speaking');
        this.buddyText.classList.remove('speaking');
        this.buddySection.classList.remove('active');
        this.resumeVAD();

        // Reset avatar state
        if (this.avatarEnabled && this.avatarManager) {
            this.avatarManager.setState('idle');
        }
    }

    completeCurrentSection() {
        if (!this.sections.length) return;

        const sectionNum = this.currentSection + 1; // 1-indexed for backend
        console.log('[StreamBuddy] Complete section:', sectionNum);

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

        console.log('[StreamBuddy] Go to previous section');

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
        console.log('[StreamBuddy] Recap section:', section?.title);

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'recap_section',
                section: this.currentSection + 1  // 1-indexed
            }));
        }
    }

    async initAvatar() {
        try {
            // Check if avatar components are loaded
            if (typeof AvatarManager === 'undefined') {
                console.warn('[StreamBuddy] AvatarManager not loaded, skipping avatar init');
                return;
            }

            this.avatarManager = new AvatarManager('avatar-canvas', {
                scale: 0.5,
                backgroundColor: 0x000000,
                backgroundAlpha: 0
            });

            await this.avatarManager.init();

            // Load default model
            const modelUrl = 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/haru/haru_greeter_t03.model3.json';
            await this.avatarManager.loadModel(modelUrl);

            this.avatarEnabled = true;
            console.log('[StreamBuddy] Avatar initialized');

            // Initialize action system
            this.initActionSystem();

        } catch (error) {
            console.warn('[StreamBuddy] Avatar initialization failed:', error);
            this.avatarEnabled = false;
        }
    }

    initActionSystem() {
        try {
            // Check if action components are loaded
            if (typeof ActionParser === 'undefined' ||
                typeof ActionLibrary === 'undefined' ||
                typeof ActionExecutor === 'undefined') {
                console.warn('[StreamBuddy] Action system not fully loaded');
                return;
            }

            this.actionParser = new ActionParser();
            this.actionLibrary = new ActionLibrary();

            // Create executor with callback to set avatar parameters
            this.actionExecutor = new ActionExecutor(
                this.actionLibrary,
                (param, value) => {
                    if (this.avatarManager) {
                        this.avatarManager.setParameter(param, value);
                    }
                },
                (partId, opacity) => {
                    if (this.avatarManager && this.avatarManager.setPartOpacity) {
                        // Disable pose system when manually controlling parts
                        // Pose system controls arm part switching and fights with manual opacity
                        if (this.avatarManager.model?.internalModel?.pose) {
                            this.avatarManager._poseDisabledByGesture = true;
                            this.avatarManager.model.internalModel.pose = null;
                        }
                        this.avatarManager.setPartOpacity(partId, opacity);
                    }
                }
            );

            // Exclude mouthOpen from action executor (controlled by lip sync)
            this.actionExecutor.excludeParam('mouthOpen');

            // Start the executor animation loop
            this.actionExecutor.start();

            // Stop the stateMachine since ActionExecutor now controls expressions
            // (They both try to set the same parameters and fight for control)
            if (this.avatarManager && this.avatarManager.stateMachine) {
                this.avatarManager.stateMachine.stop();
                console.log('[StreamBuddy] StateMachine stopped - ActionExecutor now controls avatar');
            }

            // Connect ActionExecutor to AvatarManager for hybrid server mode
            if (this.avatarManager) {
                this.avatarManager.setActionExecutor(this.actionExecutor);

                // Connect to server for hybrid mode (server sends idle behaviors at 2s intervals)
                this.avatarManager.connectServer(this.sessionId || 'buddy');
                console.log('[StreamBuddy] Hybrid server mode enabled');
            }

            console.log('[StreamBuddy] Action system initialized');
            console.log('[StreamBuddy] Available moods:', this.actionLibrary.list('moods').join(', '));
            console.log('[StreamBuddy] Available gestures:', this.actionLibrary.list('gestures').join(', '));

        } catch (error) {
            console.warn('[StreamBuddy] Action system initialization failed:', error);
        }
    }

    async startSession() {
        const script = this.scriptInput.value.trim();
        if (!script) {
            alert('Please enter a script first');
            return;
        }

        // Get selected voice, style, proactive, personality, and TTS model
        this.selectedVoice = this.voiceSelect.value;
        this.selectedStyle = this.styleSelect.value;
        this.proactiveEnabled = this.proactiveToggle?.checked || false;
        this.selectedPersonality = this.personalitySelect.value;
        this.selectedTtsModel = this.ttsModelSelect.value;
        console.log('[StreamBuddy] Starting with voice:', this.selectedVoice, 'style:', this.selectedStyle, 'proactive:', this.proactiveEnabled, 'personality:', this.selectedPersonality, 'ttsModel:', this.selectedTtsModel);

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
        this.buddySection.classList.remove('active');
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
                // Store in localStorage for popup windows (localStorage is shared across windows)
                localStorage.setItem('streambuddy_session_id', this.sessionId);
                console.log(`[StreamBuddy] Session ready: ${this.sessionId}`);

                // Reconnect avatar to server with correct session ID
                if (this.avatarManager && this.avatarManager.isServerConnected()) {
                    this.avatarManager.disconnectServer();
                }
                if (this.avatarManager && this.actionExecutor) {
                    this.avatarManager.connectServer(this.sessionId);
                    console.log(`[StreamBuddy] Avatar connected to session: ${this.sessionId}`);
                }
                // Send script, voice, style, proactive, personality, and TTS model
                this.ws.send(JSON.stringify({
                    type: 'load_script',
                    script: script,
                    voice: this.selectedVoice,
                    style: this.selectedStyle,
                    proactive: this.proactiveEnabled,
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

                // Send initial settings for auto_response and periodic_interval
                if (this.autoResponseCheckbox) {
                    this.autoResponseEnabled = this.autoResponseCheckbox.checked;
                }
                if (this.periodicIntervalSelect) {
                    this.periodicInterval = parseInt(this.periodicIntervalSelect.value) || 0;
                }
                this.ws.send(JSON.stringify({
                    type: 'set_auto_response',
                    enabled: this.autoResponseEnabled
                }));
                this.ws.send(JSON.stringify({
                    type: 'set_periodic_interval',
                    seconds: this.periodicInterval
                }));

                // Set avatar to listening state
                if (this.avatarEnabled && this.avatarManager) {
                    this.avatarManager.setState('listening');
                    this.avatarManager.setEmotion('neutral');
                }
                break;

            case 'transcript':
                console.log('[StreamBuddy] Transcript:', msg.text);
                this.addTranscript('You', msg.text);
                // Don't reset status if there's a pending response waiting
                if (!this.pendingResponseText) {
                    this.setStatus('listening', 'Listening...');
                }
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
                console.log('[StreamBuddy] Avatar enabled:', this.avatarEnabled);
                console.log('[StreamBuddy] ActionParser:', this.actionParser ? 'loaded' : 'NOT LOADED');
                console.log('[StreamBuddy] ActionExecutor:', this.actionExecutor ? 'loaded' : 'NOT LOADED');

                // Parse action tags from text WITH TIMING (defer execution until audio plays)
                let displayText = msg.text;
                this.pendingActions = null;

                if (this.actionParser && this.actionExecutor) {
                    // Use parseWithTiming - 60ms per character for speech pacing
                    const parsed = this.actionParser.parseWithTiming(msg.text, 60);
                    displayText = parsed.cleanText;
                    console.log('[StreamBuddy] Parsed result:', parsed);

                    if (parsed.actions.length > 0) {
                        console.log('[StreamBuddy] Actions parsed (will schedule on audio play):', parsed.actions);
                        // Store actions for scheduling when audio starts
                        this.pendingActions = parsed.actions;
                    } else {
                        console.log('[StreamBuddy] No action tags found in response');
                        // No explicit actions - fallback to emotion detection
                        if (this.avatarEnabled && this.avatarManager) {
                            const emotion = this.avatarManager.detectEmotion(msg.text);
                            if (this.actionExecutor) {
                                this.actionExecutor.setMood(emotion);
                            }
                            console.log('[StreamBuddy] Auto-detected emotion:', emotion);
                        }
                    }
                } else {
                    console.warn('[StreamBuddy] Action system not initialized!');
                }

                // Don't show text yet - queue will show sentences one by one
                this.buddyText.innerHTML = '';
                this.buddyText.classList.add('speaking');
                this.buddySection.classList.add('active');
                this.setStatus('thinking', 'Generating speech...');

                // Set avatar to thinking state
                if (this.avatarEnabled && this.avatarManager) {
                    this.avatarManager.setState('thinking');
                }
                break;

            case 'cohost_audio':
                console.log('[StreamBuddy] Co-host audio received (legacy single)');
                // Strip action tags from transcript display
                const transcriptText = this.actionParser
                    ? this.actionParser.stripTags(msg.text)
                    : msg.text;
                this.addTranscript(this.personaName, transcriptText);
                this.setStatus('speaking', 'Speaking...');

                // Pause VAD while playing
                this.pauseVAD();

                // Set avatar to speaking state
                if (this.avatarEnabled && this.avatarManager) {
                    this.avatarManager.setState('speaking');
                }

                if (msg.audio_base64) {
                    this.playAudio(msg.audio_base64);
                }
                break;

            case 'cohost_audio_queued':
                // New queued audio system - receives multiple chunks
                console.log('[StreamBuddy] Co-host audio queued');

                // Pause VAD while playing
                this.pauseVAD();

                // Parse actions from text
                let queuedDisplayText = msg.text;
                let queuedActions = null;

                if (this.actionParser) {
                    const parsed = this.actionParser.parseWithTiming(msg.text, 60);
                    queuedDisplayText = parsed.cleanText;
                    queuedActions = parsed.actions;
                }

                // First chunk: clear and activate buddy section
                if (this.audioQueue.length === 0 && !this.audioQueue.isPlaying) {
                    this.buddyText.innerHTML = '';  // Clear for new response
                    this.buddyText.classList.add('speaking');
                    this.buddySection.classList.add('active');
                }

                this.setStatus('speaking', 'Speaking...');

                // Enqueue audio (text will be displayed when audio starts playing)
                if (msg.audio_base64) {
                    this.audioQueue.enqueue(msg.audio_base64, queuedDisplayText, queuedActions);
                }
                break;

            case 'progress':
                this.updateProgress(msg.section, msg.progress);
                break;

            case 'reset_complete':
                console.log('[StreamBuddy] Reset complete');
                this.setStatus('listening', 'Reset complete');
                break;

            case 'response_pending':
                // Manual mode: brain has response ready, waiting for hotkey
                console.log('[StreamBuddy] Response pending (press Space):', msg.text);
                this.pendingResponseText = msg.text;

                // Show pending indicator
                this.buddySection.classList.add('pending');
                this.buddySection.classList.remove('active');

                // Strip action tags for display
                let pendingDisplayText = msg.text;
                if (this.actionParser) {
                    pendingDisplayText = this.actionParser.stripTags(msg.text);
                }

                this.buddyText.innerHTML = `
                    <span style="color: #ffcc66;">${pendingDisplayText}</span>
                    <span class="pending-indicator">Press SPACE</span>
                    <span class="hotkey-hint">Response ready - press Space to speak</span>
                `;
                this.setStatus('thinking', 'Response ready (Space to speak)');

                // Play notification sound
                this.playPendingNotification();
                break;

            case 'auto_response_changed':
                console.log('[StreamBuddy] Auto response changed:', msg.enabled);
                this.autoResponseEnabled = msg.enabled;
                if (this.autoResponseCheckbox) {
                    this.autoResponseCheckbox.checked = msg.enabled;
                }
                this.updateAutoResponseUI();
                break;

            case 'periodic_interval_changed':
                console.log('[StreamBuddy] Periodic interval changed:', msg.seconds);
                this.periodicInterval = msg.seconds;
                if (this.periodicIntervalSelect) {
                    this.periodicIntervalSelect.value = msg.seconds.toString();
                }
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

        // Start VAD for pause detection
        this.startVAD();

        console.log('[StreamBuddy] Recording started (continuous streaming with VAD)');
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

            // Get key points (max 2) - handle both dict and string format
            const keyPoints = (section.key_points || []).slice(0, 2);
            const keyPointsHtml = keyPoints.length > 0
                ? `<div class="section-points">${keyPoints.map(p => `<span>• ${typeof p === 'object' ? p.text : p}</span>`).join('')}</div>`
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
        this.currentAudioElement = audio;

        this.isPlaying = true;

        // Connect avatar lip sync to audio
        if (this.avatarEnabled && this.avatarManager) {
            this.avatarManager.connectAudio(audio);
        }

        // Schedule pending actions to sync with speech timing
        console.log('[StreamBuddy] Pending actions:', this.pendingActions);
        if (this.pendingActions && this.pendingActions.length > 0 && this.actionParser && this.actionExecutor) {
            console.log('[StreamBuddy] Scheduling', this.pendingActions.length, 'actions with timing');

            // Cancel any previously scheduled actions
            this.cancelScheduledActions();

            // Schedule new actions
            this.scheduledActionTimeouts = this.actionParser.scheduleActions(
                this.pendingActions,
                (type, name, params) => {
                    console.log('[StreamBuddy] Executing scheduled action:', type, name);
                    // Use executeFromParsed which handles all types (mood, gesture, action, eye, head, body, brow)
                    this.actionExecutor.executeFromParsed({ type, name, params: params || {} });
                }
            );

            this.pendingActions = null;
        }

        audio.onended = () => {
            console.log('[StreamBuddy] Audio playback ended');
            this.isPlaying = false;
            this.currentAudioElement = null;
            this.setStatus('listening', 'Listening...');
            this.buddyText.classList.remove('speaking');
            this.buddySection.classList.remove('active');

            // Set avatar to listening state but KEEP current emotion
            // (emotion will naturally decay or change with next response)
            if (this.avatarEnabled && this.avatarManager) {
                this.avatarManager.setState('listening');
                // Don't immediately reset emotion - let it hold
            }

            // Resume VAD
            this.resumeVAD();

            // Tell server we're ready for more audio
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ready_for_audio' }));
            }
        };

        audio.onerror = (e) => {
            console.error('[StreamBuddy] Audio playback error:', e);
            this.isPlaying = false;
            this.currentAudioElement = null;
            this.setStatus('listening', 'Listening...');

            // Cancel scheduled actions on error
            this.cancelScheduledActions();

            // Resume VAD
            this.resumeVAD();

            // Reset avatar on error
            if (this.avatarEnabled && this.avatarManager) {
                this.avatarManager.setState('idle');
            }
        };

        audio.play().catch(err => {
            console.error('[StreamBuddy] Audio play error:', err);
            this.isPlaying = false;
            this.currentAudioElement = null;
            this.cancelScheduledActions();
            this.resumeVAD();
        });
    }

    cancelScheduledActions() {
        if (this.actionParser && this.scheduledActionTimeouts.length > 0) {
            this.actionParser.cancelScheduled(this.scheduledActionTimeouts);
            this.scheduledActionTimeouts = [];
            console.log('[StreamBuddy] Cancelled scheduled actions');
        }
    }

    // VAD (Voice Activity Detection) methods
    initVAD() {
        if (!this.audioStream) return;

        try {
            this.inputAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.inputAudioContext.createMediaStreamSource(this.audioStream);

            this.inputAnalyser = this.inputAudioContext.createAnalyser();
            this.inputAnalyser.fftSize = 256;
            source.connect(this.inputAnalyser);

            console.log('[VAD] Initialized audio analyser');
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
            // Track when speech started
            if (this.speechStartTime === 0) {
                this.speechStartTime = now;
                console.log('[VAD] Speech started');
            }
            this.lastSpeechTime = now;

            // Listening animations - random nods/smiles while user speaks
            const timeSinceLastGesture = now - this.lastListeningGesture;
            if (timeSinceLastGesture > 3000 + Math.random() * 2000) {  // Every 3-5 seconds
                this.lastListeningGesture = now;
                if (this.avatarEnabled && this.actionExecutor) {
                    // Random listening gesture (mostly nods, rarely eye movements)
                    const gestures = ['nod_slow', 'nod', 'nod_slow', 'nod', 'nod_slow', 'look_up'];
                    // Smiling moods for engaged listening
                    const moods = ['friendly', 'happy', 'amused', 'interested', 'neutral'];
                    const gesture = gestures[Math.floor(Math.random() * gestures.length)];
                    const mood = moods[Math.floor(Math.random() * moods.length)];

                    // 60% chance to change mood (smile)
                    if (Math.random() > 0.4) {
                        this.actionExecutor.setMood(mood);
                    }
                    this.actionExecutor.playGesture(gesture);
                    console.log('[VAD] Listening:', gesture, mood);
                }
            }

            // Check time limit - trigger even while speaking
            const speechDuration = now - this.speechStartTime;
            if (speechDuration >= MAX_SPEECH_DURATION) {
                console.log('[VAD] Time limit reached after', speechDuration, 'ms speaking');
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'transcribe_now' }));
                }
                // Reset for next cycle
                this.speechStartTime = now;
                this.lastSpeechTime = now;
            }
        } else {
            // Silent - check for pause
            const silenceDuration = now - this.lastSpeechTime;
            if (silenceDuration >= this.pauseDuration && this.lastSpeechTime > 0 && this.speechStartTime > 0) {
                console.log('[VAD] Pause detected after', silenceDuration, 'ms silence');
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'transcribe_now' }));
                }
                // Reset for next speech segment
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

        this.vadInterval = setInterval(() => {
            this.checkVoiceActivity();
        }, VAD_CHECK_INTERVAL);

        console.log('[VAD] Started');
    }

    stopVAD() {
        this.vadEnabled = false;
        if (this.vadInterval) {
            clearInterval(this.vadInterval);
            this.vadInterval = null;
        }
        console.log('[VAD] Stopped');
    }

    resumeVAD() {
        if (!this.vadInterval) return; // Not initialized
        this.vadEnabled = true;
        this.lastSpeechTime = Date.now();
        this.speechStartTime = 0;  // Reset speech tracking
        console.log('[VAD] Resumed');
    }

    pauseVAD() {
        this.vadEnabled = false;
        console.log('[VAD] Paused');
    }

    // Play single audio with callback (used by AudioQueue)
    playSingleAudio(base64Audio, text, actions, onComplete) {
        console.log('[StreamBuddy] Playing single audio:', text.substring(0, 50));

        const audio = new Audio('data:audio/mp3;base64,' + base64Audio);
        audio.volume = 0.8;
        this.currentAudioElement = audio;
        this.isPlaying = true;

        // Add sentence to buddy text with fade-in
        const sentenceEl = document.createElement('span');
        sentenceEl.className = 'buddy-sentence current';
        sentenceEl.textContent = text;
        this.buddyText.appendChild(sentenceEl);

        // Add to transcript
        this.addTranscript(this.personaName, text);

        // Connect avatar lip sync to audio
        if (this.avatarEnabled && this.avatarManager) {
            this.avatarManager.connectAudio(audio);
            this.avatarManager.setState('speaking');
        }

        // Schedule actions if provided
        if (actions && actions.length > 0 && this.actionParser && this.actionExecutor) {
            console.log('[StreamBuddy] Scheduling', actions.length, 'actions');
            this.cancelScheduledActions();
            this.scheduledActionTimeouts = this.actionParser.scheduleActions(
                actions,
                (type, name, params) => {
                    this.actionExecutor.executeFromParsed({ type, name, params: params || {} });
                }
            );
        }

        audio.onended = () => {
            console.log('[StreamBuddy] Single audio ended');
            this.isPlaying = false;
            this.currentAudioElement = null;

            // Remove 'current' highlight from this sentence
            sentenceEl.classList.remove('current');

            if (this.avatarEnabled && this.avatarManager) {
                this.avatarManager.setState('listening');
            }

            if (onComplete) onComplete();
        };

        audio.onerror = (e) => {
            console.error('[StreamBuddy] Audio error:', e);
            this.isPlaying = false;
            this.currentAudioElement = null;
            this.cancelScheduledActions();
            if (onComplete) onComplete();
        };

        audio.play().catch(err => {
            console.error('[StreamBuddy] Audio play error:', err);
            this.isPlaying = false;
            this.currentAudioElement = null;
            this.cancelScheduledActions();
            if (onComplete) onComplete();
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
                if (settings.proactive !== undefined && this.proactiveToggle) {
                    this.proactiveToggle.checked = settings.proactive;
                }
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
                proactive: this.proactiveToggle?.checked || false,
                personality: this.personalitySelect.value,
                ttsModel: this.ttsModelSelect.value
            };
            localStorage.setItem('streambuddy_settings', JSON.stringify(settings));
            console.log('[StreamBuddy] Settings saved');
        } catch (e) {
            console.warn('[StreamBuddy] Failed to save settings:', e);
        }
    }

    // Notification sound for pending response
    playPendingNotification() {
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            oscillator.frequency.value = 800;
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
            console.log('[StreamBuddy] Could not play notification sound:', e);
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
