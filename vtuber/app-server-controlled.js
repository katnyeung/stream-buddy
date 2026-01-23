/**
 * Live2D Avatar - Server-Controlled Renderer
 *
 * This is a "dumb renderer" - all animation logic runs on the server.
 * The browser only:
 * 1. Receives parameters via WebSocket
 * 2. Applies them to the Live2D model
 * 3. Plays TTS audio and sends amplitude back for lip sync
 */

// Parameter aliases for different model formats
const PARAM_MAP = {
    angleX: ['ParamAngleX', 'PARAM_ANGLE_X'],
    angleY: ['ParamAngleY', 'PARAM_ANGLE_Y'],
    angleZ: ['ParamAngleZ', 'PARAM_ANGLE_Z'],
    mouthOpen: ['ParamMouthOpenY', 'PARAM_MOUTH_OPEN_Y'],
    mouthForm: ['ParamMouthForm', 'PARAM_MOUTH_FORM'],
    eyeOpenL: ['ParamEyeLOpen', 'PARAM_EYE_L_OPEN'],
    eyeOpenR: ['ParamEyeROpen', 'PARAM_EYE_R_OPEN'],
    eyeBallX: ['ParamEyeBallX', 'PARAM_EYE_BALL_X'],
    eyeBallY: ['ParamEyeBallY', 'PARAM_EYE_BALL_Y'],
    browLY: ['ParamBrowLY', 'PARAM_BROW_L_Y'],
    browRY: ['ParamBrowRY', 'PARAM_BROW_R_Y'],
    bodyAngleX: ['ParamBodyAngleX', 'PARAM_BODY_ANGLE_X'],
    bodyAngleY: ['ParamBodyAngleY', 'PARAM_BODY_ANGLE_Y'],
    bodyAngleZ: ['ParamBodyAngleZ', 'PARAM_BODY_ANGLE_Z'],
    armLA: ['ParamArmLA'],
    armRA: ['ParamArmRA'],
    armLB: ['ParamArmLB'],
    armRB: ['ParamArmRB'],
    handChangeL: ['ParamHandDhangeL'],
    handChangeR: ['ParamHandChangeR'],
    handAngleL: ['ParamHandAngleL'],
    handAngleR: ['ParamHandAngleR'],
    eyeSmileL: ['ParamEyeLSmile'],
    eyeSmileR: ['ParamEyeRSmile'],
    tear: ['ParamTear'],
    tere: ['ParamTere'],
    breath: ['ParamBreath']
};

class ServerControlledAvatar {
    constructor(avatarId = 'buddy') {
        this.avatarId = avatarId;
        this.app = null;
        this.model = null;
        this.ws = null;

        // Audio
        this.audioContext = null;
        this.analyser = null;
        this.dataArray = null;
        this.audioQueue = [];
        this.isPlayingAudio = false;

        // Lip sync
        this.sensitivity = 1.5;
        this.smoothedVolume = 0;

        // State
        this.connected = false;
        this.currentState = 'idle';
        this.currentMood = 'neutral';

        // Callbacks
        this.onStateChange = null;
        this.onMoodChange = null;
        this.onConnect = null;
        this.onDisconnect = null;
    }

    async init(canvasId = 'avatar-canvas', modelUrl = null) {
        console.log('[Avatar] Initializing server-controlled avatar...');

        // Check dependencies
        if (typeof PIXI === 'undefined') {
            throw new Error('PIXI.js not loaded');
        }
        if (typeof PIXI.live2d === 'undefined') {
            throw new Error('pixi-live2d-display not loaded');
        }

        // Create PIXI app
        const canvas = document.getElementById(canvasId);
        const container = canvas.parentElement;

        this.app = new PIXI.Application({
            view: canvas,
            width: container.clientWidth,
            height: container.clientHeight,
            backgroundColor: 0x1a1a2e,
            backgroundAlpha: 0,
            resolution: window.devicePixelRatio || 1,
            autoDensity: true
        });

        // Handle resize
        window.addEventListener('resize', () => this.handleResize());

        // Setup audio
        this.setupAudio();

        // Load model if URL provided
        if (modelUrl) {
            await this.loadModel(modelUrl);
        }

        console.log('[Avatar] Initialized');
    }

    async loadModel(url) {
        console.log('[Avatar] Loading model:', url);

        // Remove existing model
        if (this.model) {
            this.app.stage.removeChild(this.model);
            this.model.destroy();
            this.model = null;
        }

        const { Live2DModel } = PIXI.live2d;
        this.model = await Live2DModel.from(url, { autoInteract: false });

        // CRITICAL: Disable ALL Live2D auto-behaviors
        // Server controls everything
        const internalModel = this.model.internalModel;

        if (internalModel.motionManager) {
            internalModel.motionManager.stopAllMotions();
            internalModel.motionManager.update = () => false;
        }
        if (internalModel.expressionManager) {
            internalModel.expressionManager.update = () => false;
        }
        internalModel.physics = null;
        internalModel.pose = null;
        internalModel.eyeBlink = null;
        internalModel.breath = null;

        // Position model
        this.positionModel();

        // Add ticker for parameter application
        this.app.ticker.add(() => {
            // Parameters are applied via WebSocket messages
            // This ticker is for smooth animation
        });

        this.app.stage.addChild(this.model);

        console.log('[Avatar] Model loaded, all auto-behaviors disabled');
        window.model = this.model;
    }

    positionModel() {
        if (!this.model) return;

        const container = this.app.view.parentElement;
        const width = container.clientWidth;
        const height = container.clientHeight;

        const scale = Math.min(width / 1200, height / 1200) * 0.4;
        this.model.scale.set(scale);
        this.model.anchor.set(0.5, 0.5);
        this.model.x = width / 2;
        this.model.y = height / 2 + height * 0.15;
    }

    handleResize() {
        if (!this.app) return;
        const container = this.app.view.parentElement;
        this.app.renderer.resize(container.clientWidth, container.clientHeight);
        this.positionModel();
    }

    // === WebSocket Connection ===

    connect(wsUrl = null) {
        if (this.ws) {
            this.ws.close();
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const defaultUrl = `${protocol}//${window.location.host}/ws/avatar/${this.avatarId}`;
        const url = wsUrl || defaultUrl;

        console.log('[Avatar] Connecting to:', url);

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            console.log('[Avatar] WebSocket connected');
            this.connected = true;
            if (this.onConnect) this.onConnect();
        };

        this.ws.onclose = () => {
            console.log('[Avatar] WebSocket disconnected');
            this.connected = false;
            if (this.onDisconnect) this.onDisconnect();

            // Attempt reconnect after 3 seconds
            setTimeout(() => {
                if (!this.connected) {
                    console.log('[Avatar] Attempting reconnect...');
                    this.connect(url);
                }
            }, 3000);
        };

        this.ws.onerror = (error) => {
            console.error('[Avatar] WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            this.handleMessage(JSON.parse(event.data));
        };
    }

    disconnect() {
        if (this.ws) {
            this.connected = false;
            this.ws.close();
            this.ws = null;
        }
    }

    handleMessage(msg) {
        switch (msg.type) {
            case 'init':
                console.log('[Avatar] Initialized:', msg);
                this.currentState = msg.state;
                this.currentMood = msg.mood;
                break;

            case 'params':
                // Apply parameters from server
                this.applyParams(msg.data);
                break;

            case 'state':
                this.currentState = msg.state;
                if (this.onStateChange) this.onStateChange(msg.state);
                break;

            case 'mood':
                this.currentMood = msg.mood;
                if (this.onMoodChange) this.onMoodChange(msg.mood);
                break;

            case 'speech':
                // Queue speech for playback
                this.queueSpeech(msg.text, msg.audio_base64);
                break;
        }
    }

    // === Parameter Application ===

    applyParams(params) {
        if (!this.model) return;

        for (const [key, value] of Object.entries(params)) {
            this.setParam(key, value);
        }
    }

    setParam(key, value) {
        if (!this.model) return false;

        const coreModel = this.model.internalModel.coreModel;
        const aliases = PARAM_MAP[key] || [key];

        for (const name of aliases) {
            try {
                // Cubism 4 API
                if (typeof coreModel.getParameterIndex === 'function') {
                    const idx = coreModel.getParameterIndex(name);
                    if (idx >= 0) {
                        coreModel.setParameterValueByIndex(idx, value);
                        return true;
                    }
                }
                // Cubism 2 API
                else if (coreModel._parameterIds || coreModel.parameterIds) {
                    const ids = coreModel._parameterIds || coreModel.parameterIds;
                    const idx = ids.indexOf(name);
                    if (idx >= 0) {
                        if (coreModel.setParamFloat) {
                            coreModel.setParamFloat(name, value);
                            return true;
                        } else if (coreModel._parameterValues) {
                            coreModel._parameterValues[idx] = value;
                            return true;
                        }
                    }
                }
            } catch (e) {
                // Continue to next alias
            }
        }
        return false;
    }

    setPartOpacity(partIdOrIndex, opacity) {
        if (!this.model) return false;

        const coreModel = this.model.internalModel.coreModel;

        try {
            // Cubism 2
            if (coreModel._partIds && coreModel._partOpacities) {
                let index = partIdOrIndex;
                if (typeof partIdOrIndex === 'string') {
                    index = coreModel._partIds.indexOf(partIdOrIndex);
                }
                if (index >= 0 && index < coreModel._partOpacities.length) {
                    coreModel._partOpacities[index] = opacity;
                    return true;
                }
            }
            // Cubism 4
            else if (typeof coreModel.setPartOpacityByIndex === 'function') {
                let index = partIdOrIndex;
                if (typeof partIdOrIndex === 'string') {
                    const count = coreModel.getPartCount();
                    for (let i = 0; i < count; i++) {
                        if (coreModel.getPartId(i) === partIdOrIndex) {
                            index = i;
                            break;
                        }
                    }
                }
                coreModel.setPartOpacityByIndex(index, opacity);
                return true;
            }
        } catch (e) {
            console.error('Error setting part opacity:', e);
        }
        return false;
    }

    // === Audio / Lip Sync ===

    setupAudio() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.5;
        this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    }

    queueSpeech(text, audioBase64) {
        this.audioQueue.push({ text, audioBase64 });
        if (!this.isPlayingAudio) {
            this.playNextAudio();
        }
    }

    async playNextAudio() {
        if (this.audioQueue.length === 0) {
            this.isPlayingAudio = false;
            // Notify server we're ready
            this.send({ type: 'ready' });
            return;
        }

        this.isPlayingAudio = true;
        const item = this.audioQueue.shift();

        if (!item.audioBase64) {
            this.playNextAudio();
            return;
        }

        try {
            // Resume audio context if suspended
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }

            // Create audio element
            const audio = new Audio(`data:audio/mp3;base64,${item.audioBase64}`);

            // Connect to analyser for lip sync
            const source = this.audioContext.createMediaElementSource(audio);
            source.connect(this.analyser);
            this.analyser.connect(this.audioContext.destination);

            // Start lip sync sending
            this.startLipSyncSending();

            // Play and wait for end
            await new Promise((resolve, reject) => {
                audio.onended = resolve;
                audio.onerror = reject;
                audio.play().catch(reject);
            });

            // Stop lip sync
            this.stopLipSyncSending();

        } catch (error) {
            console.error('[Avatar] Audio playback error:', error);
        }

        // Play next
        this.playNextAudio();
    }

    startLipSyncSending() {
        this._lipSyncInterval = setInterval(() => {
            const amplitude = this.getAmplitude();
            this.send({ type: 'lipsync', amplitude });
        }, 1000 / 24);  // 24fps
    }

    stopLipSyncSending() {
        if (this._lipSyncInterval) {
            clearInterval(this._lipSyncInterval);
            this._lipSyncInterval = null;
        }
        // Send zero amplitude
        this.send({ type: 'lipsync', amplitude: 0 });
    }

    getAmplitude() {
        if (!this.analyser) return 0;

        this.analyser.getByteFrequencyData(this.dataArray);

        let sum = 0;
        for (let i = 2; i < 20; i++) {
            sum += this.dataArray[i];
        }

        const avg = sum / 18 / 255;
        this.smoothedVolume = this.smoothedVolume * 0.3 + avg * 0.7;

        return Math.min(1, Math.pow(this.smoothedVolume, 0.7) * this.sensitivity);
    }

    // === Communication ===

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    // === Control API (sends to server) ===

    setState(state) {
        this.send({ type: 'set_state', state });
    }

    setMood(mood, intensity = 1.0) {
        this.send({ type: 'set_mood', mood, intensity });
    }

    triggerGesture(name, params = {}) {
        this.send({ type: 'gesture', name, params });
    }

    triggerAction(actionType, name, params = {}) {
        this.send({ type: 'action', action_type: actionType, name, params });
    }

    setPersonality(name) {
        this.send({ type: 'personality', name });
    }
}

// Export for use
window.ServerControlledAvatar = ServerControlledAvatar;

// Auto-initialize if config exists
document.addEventListener('DOMContentLoaded', async () => {
    const canvas = document.getElementById('avatar-canvas');
    if (!canvas) return;

    const config = window.avatarConfig || {};
    const avatar = new ServerControlledAvatar(config.avatarId || 'buddy');

    await avatar.init('avatar-canvas', config.modelUrl);

    if (config.autoConnect !== false) {
        avatar.connect(config.wsUrl);
    }

    window.avatar = avatar;
    console.log('[Avatar] Ready - window.avatar available');
});
