/**
 * Live2D Avatar Test Application
 * Access via: http://localhost:8000/vtuber/
 */

// Expression presets
const EXPRESSIONS = {
    neutral: { angleX: 0, angleY: 0, angleZ: 0, mouthOpen: 0, mouthForm: 0, eyeOpenL: 1, eyeOpenR: 1 },
    happy: { angleX: 5, angleY: -3, angleZ: 5, mouthOpen: 0.2, mouthForm: 0.8, eyeOpenL: 0.7, eyeOpenR: 0.7 },
    thinking: { angleX: -15, angleY: 10, angleZ: 8, mouthOpen: 0, mouthForm: 0.1, eyeOpenL: 0.8, eyeOpenR: 0.5 },
    surprised: { angleX: 0, angleY: -8, angleZ: 0, mouthOpen: 0.7, mouthForm: 0, eyeOpenL: 1.2, eyeOpenR: 1.2 },
    sad: { angleX: -5, angleY: 12, angleZ: -3, mouthOpen: 0.1, mouthForm: -0.5, eyeOpenL: 0.6, eyeOpenR: 0.6 },
    excited: { angleX: 3, angleY: -5, angleZ: 8, mouthOpen: 0.4, mouthForm: 1, eyeOpenL: 1.1, eyeOpenR: 1.1 }
};

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
    // Arms - A is rotation (-1 to 1), B is lift (-1 to 5)
    armLA: ['ParamArmLA'],
    armRA: ['ParamArmRA'],
    armLB: ['ParamArmLB'],  // Lift left arm up (0-5)
    armRB: ['ParamArmRB'],  // Lift right arm up (0-5)
    // Hands - Change is pose (0-1), Angle is rotation (-1 to 1)
    handChangeL: ['ParamHandDhangeL'],  // Note: typo in model "Dhange"
    handChangeR: ['ParamHandChangeR'],
    handAngleL: ['ParamHandAngleL'],
    handAngleR: ['ParamHandAngleR'],
    // Extra
    eyeSmileL: ['ParamEyeLSmile'],
    eyeSmileR: ['ParamEyeRSmile'],
    tear: ['ParamTear'],
    tere: ['ParamTere'],  // Blush?
    breath: ['ParamBreath']
};

class AvatarTest {
    constructor() {
        this.app = null;
        this.model = null;
        this.statusEl = document.getElementById('status');
        this.volumeFill = document.getElementById('volume-fill');
        this.testAudio = document.getElementById('test-audio');

        // Audio
        this.audioContext = null;
        this.analyser = null;
        this.dataArray = null;
        this.isLipSyncActive = false;
        this.sensitivity = 1.5;
        this.smoothedVolume = 0;
        this.micStream = null;
        this.audioSource = null;

        // Manual parameter values (persisted so we can re-apply each frame)
        this.manualParams = {};
        this.manualParamTimestamps = {};  // Track when each param was last set
        this.manualMode = true;  // When true, override model's internal updates

        // Control mode: 'strict' | 'hold' | 'auto'
        this.controlMode = 'strict';

        // Auto mode settings
        this.overrideHoldTime = 8000;  // How long to hold override before releasing (ms)
        this.overrideFadeTime = 2000;  // How long to fade out the override (ms)

        // Hold+Idle mode settings
        this.idleTime = 0;
        this.lastTickTime = 0;

        // Action system
        this.actionParser = null;
        this.actionLibrary = null;
        this.actionExecutor = null;
    }

    async init() {
        this.setStatus('loading', 'Initializing...');

        try {
            // Check dependencies
            if (typeof PIXI === 'undefined') {
                throw new Error('PIXI.js not loaded');
            }
            if (typeof PIXI.live2d === 'undefined') {
                throw new Error('pixi-live2d-display not loaded. Make sure live2dcubismcore.js is loaded first.');
            }

            // Create PIXI app (v6 API)
            const canvas = document.getElementById('avatar-canvas');
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

            // Setup controls
            this.setupControls();

            // Load default model
            await this.loadModel(document.getElementById('model-url').value);

        } catch (err) {
            this.setStatus('error', err.message);
            console.error('[AvatarTest] Init failed:', err);
        }
    }

    async loadModel(url) {
        if (!url) return;

        this.setStatus('loading', 'Loading model...');

        // Remove existing model
        if (this.model) {
            this.app.stage.removeChild(this.model);
            this.model.destroy();
            this.model = null;
        }

        try {
            const { Live2DModel } = PIXI.live2d;

            this.model = await Live2DModel.from(url, { autoInteract: false });

            // Store original internal model components for mode switching
            const internalModel = this.model.internalModel;
            this._originalPhysics = internalModel.physics;
            this._originalPose = internalModel.pose;
            this._originalEyeBlink = internalModel.eyeBlink;
            this._originalBreath = internalModel.breath;
            this._originalMotionManagerUpdate = internalModel.motionManager?.update?.bind(internalModel.motionManager);
            this._originalExpressionManagerUpdate = internalModel.expressionManager?.update?.bind(internalModel.expressionManager);

            // Apply current mode
            this.applyControlMode();

            // Initialize tick time
            this.lastTickTime = performance.now();

            // Add ticker for parameter updates
            this.app.ticker.add(() => {
                if (!this.model) return;

                const now = performance.now();
                const deltaTime = now - this.lastTickTime;
                this.lastTickTime = now;

                switch (this.controlMode) {
                    case 'strict':
                        // Strict: apply manual params exactly, no animation
                        this.applyManualParams();
                        break;
                    case 'hold':
                        // Hold+Auto: Live2D animates, user position as offset
                        this.applyHoldAutoMode();
                        break;
                    case 'auto':
                        // Auto: temporary overrides, then release to Live2D
                        this.applyAutoModeOverrides();
                        break;
                }
            });

            // Position model
            this.positionModel();

            // Add to stage
            this.app.stage.addChild(this.model);

            this.setStatus('ready', 'Model loaded!');
            console.log('[AvatarTest] Model loaded:', url);
            console.log('[AvatarTest] Tip: Idle motions disabled for manual control');

            // Store for debugging
            window.model = this.model;

        } catch (err) {
            this.setStatus('error', 'Failed to load model');
            console.error('[AvatarTest] Load failed:', err);
        }
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
        const container = this.app.view.parentElement;
        this.app.renderer.resize(container.clientWidth, container.clientHeight);
        this.positionModel();
    }

    setStatus(type, text) {
        this.statusEl.textContent = text;
        this.statusEl.className = 'status ' + type;
    }

    // Set a model parameter (stores for continuous re-application)
    setParam(key, value) {
        // Store in manual params so it persists
        this.manualParams[key] = value;
        this.manualParamTimestamps[key] = performance.now();  // Track when set

        // Also apply immediately
        this.applyParam(key, value);
    }

    // Apply a single parameter to the model
    applyParam(key, value) {
        if (!this.model) return false;

        const coreModel = this.model.internalModel.coreModel;
        const aliases = PARAM_MAP[key] || [key];

        for (const name of aliases) {
            try {
                // Try Cubism 4 API
                if (typeof coreModel.getParameterIndex === 'function') {
                    const idx = coreModel.getParameterIndex(name);
                    if (idx >= 0) {
                        coreModel.setParameterValueByIndex(idx, value);
                        return true;
                    }
                }
                // Try Cubism 2 API
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

    // Re-apply all manual parameters (called each frame to override model's internal updates)
    applyManualParams() {
        for (const [key, value] of Object.entries(this.manualParams)) {
            this.applyParam(key, value);
        }
    }

    // Hold+Auto mode: Apply user params directly, let physics/breath/blink add subtle life
    applyHoldAutoMode() {
        // Since motionManager is disabled (no idle loop), we apply user params directly
        // Physics will add hair movement, breath adds subtle body sway, eyeBlink handles blinking
        // These don't fight with head position because they affect different parameters

        for (const [key, value] of Object.entries(this.manualParams)) {
            this.applyParam(key, value);
        }
    }

    // Auto mode: apply manual overrides with timeout/fade, let Live2D handle the rest
    applyAutoModeOverrides() {
        const now = performance.now();

        for (const [key, value] of Object.entries(this.manualParams)) {
            const setTime = this.manualParamTimestamps[key] || 0;
            const elapsed = now - setTime;

            if (elapsed < this.overrideHoldTime) {
                // Within hold time: full override
                this.applyParam(key, value);
            } else if (elapsed < this.overrideHoldTime + this.overrideFadeTime) {
                // In fade period: blend between manual value and Live2D
                // We apply the manual value but Live2D will also try to update
                // The blend happens naturally as we apply less frequently
                const fadeProgress = (elapsed - this.overrideHoldTime) / this.overrideFadeTime;
                // Only apply if we're in the early part of fade
                if (fadeProgress < 0.5) {
                    this.applyParam(key, value);
                }
                // After 50% fade, let Live2D fully take over
            }
            // After fade period: don't apply, let Live2D control
        }
    }

    // Set control mode: 'strict' | 'hold' | 'auto'
    setControlMode(mode) {
        this.controlMode = mode;
        this.applyControlMode();
        console.log(`[AvatarTest] Control mode: ${mode}`);
    }

    // Apply the current control mode settings
    applyControlMode() {
        if (!this.model) return;

        const internalModel = this.model.internalModel;

        if (this.controlMode === 'strict') {
            // === STRICT MODE: Disable ALL Live2D internals ===
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

            console.log('[AvatarTest] Strict mode: Parameters stay exactly where set (frozen)');

        } else if (this.controlMode === 'hold') {
            // === HOLD+AUTO MODE: Keep subtle movement, but NO idle motion loops ===
            // Disable motionManager - it plays idle animation loops that have "return to center" keyframes
            if (internalModel.motionManager) {
                internalModel.motionManager.stopAllMotions();
                internalModel.motionManager.update = () => false;
            }
            // Disable expression manager (expressions also override params)
            if (internalModel.expressionManager) {
                internalModel.expressionManager.update = () => false;
            }
            // KEEP these for natural subtle movement:
            // - physics: hair/clothing responds to movement
            // - breath: subtle breathing animation
            // - eyeBlink: automatic natural blinking
            // - pose: ensures proper bone positions (but disabled during arm gestures)
            if (this._originalPhysics) internalModel.physics = this._originalPhysics;
            // Only restore pose if not disabled by gesture (pose controls arm part switching)
            if (this._originalPose && !this._poseDisabledByGesture) {
                internalModel.pose = this._originalPose;
            }
            if (this._originalEyeBlink) internalModel.eyeBlink = this._originalEyeBlink;
            if (this._originalBreath) internalModel.breath = this._originalBreath;

            console.log('[AvatarTest] Hold+Auto mode: Natural movement (physics/breath/blink) + user position held');

        } else {
            // === AUTO MODE: Full Live2D animations + temporary overrides ===
            // Restore motion manager for full idle animations
            if (internalModel.motionManager && this._originalMotionManagerUpdate) {
                internalModel.motionManager.update = this._originalMotionManagerUpdate;
            }
            // Restore expression manager
            if (internalModel.expressionManager && this._originalExpressionManagerUpdate) {
                internalModel.expressionManager.update = this._originalExpressionManagerUpdate;
            }
            // Restore all
            if (this._originalPhysics) internalModel.physics = this._originalPhysics;
            // Only restore pose if not disabled by gesture
            if (this._originalPose && !this._poseDisabledByGesture) {
                internalModel.pose = this._originalPose;
            }
            if (this._originalEyeBlink) internalModel.eyeBlink = this._originalEyeBlink;
            if (this._originalBreath) internalModel.breath = this._originalBreath;

            console.log('[AvatarTest] Auto mode: Full Live2D animations + temporary overrides (~8s)');
        }
    }

    // Apply expression preset
    applyExpression(name) {
        const preset = EXPRESSIONS[name];
        if (!preset) return;

        Object.entries(preset).forEach(([key, value]) => {
            this.setParam(key, value);

            // Update slider UI
            const slider = document.getElementById(key);
            const valEl = document.getElementById(`${key}-val`);
            if (slider) slider.value = value;
            if (valEl) valEl.textContent = typeof value === 'number' ? value.toFixed(2) : value;
        });
    }

    // Audio setup for lip sync
    setupAudio() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.5;
        this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    }

    connectAudio(audioEl) {
        try {
            const source = this.audioContext.createMediaElementSource(audioEl);
            source.connect(this.analyser);
            this.analyser.connect(this.audioContext.destination);
            return true;
        } catch (e) {
            console.warn('[AvatarTest] Audio already connected or error:', e.message);
            return false;
        }
    }

    getVolume() {
        if (!this.analyser) return 0;

        this.analyser.getByteFrequencyData(this.dataArray);

        let sum = 0;
        for (let i = 2; i < 20; i++) {
            sum += this.dataArray[i];
        }

        const avg = sum / 18 / 255;
        this.smoothedVolume = this.smoothedVolume * 0.3 + avg * 0.7;
        return this.smoothedVolume;
    }

    getMouthValue() {
        const vol = this.getVolume();
        return Math.min(1, Math.pow(vol, 0.7) * this.sensitivity);
    }

    startLipSync() {
        if (this.isLipSyncActive) return;
        this.isLipSyncActive = true;

        const animate = () => {
            if (!this.isLipSyncActive) return;

            const mouth = this.getMouthValue();
            this.setParam('mouthOpen', mouth);
            this.volumeFill.style.width = `${mouth * 100}%`;

            // Update slider
            const slider = document.getElementById('mouthOpen');
            const valEl = document.getElementById('mouthOpen-val');
            if (slider) slider.value = mouth;
            if (valEl) valEl.textContent = mouth.toFixed(2);

            requestAnimationFrame(animate);
        };
        animate();
    }

    stopLipSync() {
        this.isLipSyncActive = false;
        this.volumeFill.style.width = '0%';
    }

    listParameters() {
        if (!this.model) return 'No model loaded';

        const internalModel = this.model.internalModel;
        const coreModel = internalModel.coreModel;
        let output = '';

        try {
            // Check for Cubism 2 API first (has _parameterIds)
            if (coreModel._parameterIds) {
                const ids = coreModel._parameterIds;
                const values = coreModel._parameterValues;
                const mins = coreModel._parameterMinimumValues;
                const maxs = coreModel._parameterMaximumValues;
                output = `[Cubism 2] Found ${ids.length} parameters:\n\n`;

                for (let i = 0; i < ids.length; i++) {
                    const id = ids[i];
                    const val = values ? values[i] : 0;
                    const min = mins ? mins[i] : 0;
                    const max = maxs ? maxs[i] : 1;
                    output += `${id}: ${val.toFixed(2)} (${min} to ${max})\n`;
                }
            }
            // Try Cubism 4 API
            else if (typeof coreModel.getParameterId === 'function') {
                const count = coreModel.getParameterCount();
                output = `[Cubism 4] Found ${count} parameters:\n\n`;

                for (let i = 0; i < count; i++) {
                    const id = coreModel.getParameterId(i);
                    const val = coreModel.getParameterValueByIndex(i);
                    const min = coreModel.getParameterMinimumValue(i);
                    const max = coreModel.getParameterMaximumValue(i);
                    output += `${id}: ${val.toFixed(2)} (${min} to ${max})\n`;
                }
            }
            // Try alternative access via model settings
            else if (internalModel.settings?.parameters) {
                const params = internalModel.settings.parameters;
                output = `[Settings] Found ${params.length} parameters:\n\n`;
                params.forEach(p => {
                    output += `${p.id || p.Id}: default ${p.default || 0} (${p.min || 0} to ${p.max || 1})\n`;
                });
            }
            // Last resort - inspect the object
            else {
                output = 'Unknown model format. CoreModel keys:\n';
                output += Object.keys(coreModel).join('\n');
            }
        } catch (e) {
            output = 'Error: ' + e.message + '\n\nCoreModel keys: ';
            output += Object.keys(coreModel || {}).join(', ');
        }
        return output;
    }

    listParts() {
        if (!this.model) return 'No model loaded';

        const internalModel = this.model.internalModel;
        const coreModel = internalModel.coreModel;
        let output = '';

        try {
            // Check for Cubism 2 API (has _partIds)
            if (coreModel._partIds) {
                const ids = coreModel._partIds;
                const opacities = coreModel._partOpacities;
                output = `[Cubism 2] Found ${ids.length} parts:\n\n`;

                for (let i = 0; i < ids.length; i++) {
                    const id = ids[i];
                    const opacity = opacities ? opacities[i] : 1;
                    output += `${i}: ${id} (opacity: ${opacity.toFixed(2)})\n`;
                }
            }
            // Try Cubism 4 API
            else if (typeof coreModel.getPartCount === 'function') {
                const count = coreModel.getPartCount();
                output = `[Cubism 4] Found ${count} parts:\n\n`;

                for (let i = 0; i < count; i++) {
                    const id = coreModel.getPartId(i);
                    output += `${i}: ${id}\n`;
                }
            }
            // Last resort - inspect the object
            else {
                output = 'Unknown model format. Looking for part-related keys:\n';
                const keys = Object.keys(coreModel);
                const partKeys = keys.filter(k => k.toLowerCase().includes('part'));
                output += partKeys.length > 0 ? partKeys.join('\n') : 'No part keys found\n';
                output += '\nAll keys: ' + keys.join(', ');
            }
        } catch (e) {
            output = 'Error: ' + e.message + '\n\nCoreModel keys: ';
            output += Object.keys(coreModel || {}).join(', ');
        }
        return output;
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

    /**
     * Restore pose system control (let model handle arm part switching)
     */
    restorePoseControl() {
        if (!this.model) return;

        this._poseDisabledByGesture = false;
        if (this._originalPose) {
            this.model.internalModel.pose = this._originalPose;
            console.log('[AvatarTest] Pose control restored to model');
        }

        // Also reset action executor's arm state
        if (this.actionExecutor) {
            this.actionExecutor.armPartState = null;
        }
    }

    setupControls() {
        // Model loading
        document.getElementById('load-model-btn').addEventListener('click', () => {
            this.loadModel(document.getElementById('model-url').value);
        });

        // Control mode toggle
        const strictBtn = document.getElementById('mode-strict-btn');
        const holdBtn = document.getElementById('mode-hold-btn');
        const autoBtn = document.getElementById('mode-auto-btn');

        const setActiveButton = (activeBtn) => {
            strictBtn.classList.remove('active-mode');
            holdBtn.classList.remove('active-mode');
            autoBtn.classList.remove('active-mode');
            activeBtn.classList.add('active-mode');
        };

        strictBtn.addEventListener('click', () => {
            this.setControlMode('strict');
            setActiveButton(strictBtn);
        });

        holdBtn.addEventListener('click', () => {
            this.setControlMode('hold');
            setActiveButton(holdBtn);
        });

        autoBtn.addEventListener('click', () => {
            this.setControlMode('auto');
            setActiveButton(autoBtn);
        });

        // Sliders
        const sliders = ['angleX', 'angleY', 'angleZ', 'mouthOpen', 'mouthForm',
                        'eyeOpenL', 'eyeOpenR', 'eyeBallX', 'eyeBallY',
                        'armLB', 'armRB', 'armLA', 'armRA', 'handChangeL', 'handChangeR'];

        sliders.forEach(id => {
            const slider = document.getElementById(id);
            const valEl = document.getElementById(`${id}-val`);

            if (slider) {
                slider.addEventListener('input', (e) => {
                    const val = parseFloat(e.target.value);
                    if (valEl) valEl.textContent = val.toFixed(2);
                    this.setParam(id, val);
                });
            }
        });

        // Expression buttons
        document.querySelectorAll('[data-expression]').forEach(btn => {
            btn.addEventListener('click', () => {
                this.applyExpression(btn.dataset.expression);
            });
        });

        // Reset
        document.getElementById('reset-btn').addEventListener('click', () => {
            this.applyExpression('neutral');
        });

        // Audio controls
        let audioConnected = false;

        // File picker - load local audio file (no CORS issues)
        document.getElementById('audio-file').addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                const url = URL.createObjectURL(file);
                this.testAudio.src = url;
                console.log('[AvatarTest] Local audio file loaded:', file.name);
            }
        });

        document.getElementById('play-audio-btn').addEventListener('click', () => {
            if (this.audioContext.state === 'suspended') {
                this.audioContext.resume();
            }

            if (!this.testAudio.src) {
                alert('Please select an audio file first using the file picker above.');
                return;
            }

            if (!audioConnected) {
                audioConnected = this.connectAudio(this.testAudio);
            }

            this.testAudio.play();
            this.startLipSync();
        });

        document.getElementById('stop-audio-btn').addEventListener('click', () => {
            this.testAudio.pause();
            this.testAudio.currentTime = 0;
            this.stopLipSync();
            this.setParam('mouthOpen', 0);
        });

        // Microphone - real-time lip sync testing
        document.getElementById('mic-btn').addEventListener('click', async () => {
            try {
                if (this.audioContext.state === 'suspended') {
                    await this.audioContext.resume();
                }

                // Stop any existing mic stream
                if (this.micStream) {
                    this.micStream.getTracks().forEach(t => t.stop());
                }

                // Get microphone access
                this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const source = this.audioContext.createMediaStreamSource(this.micStream);
                source.connect(this.analyser);
                // Don't connect to destination to avoid feedback

                this.startLipSync();
                console.log('[AvatarTest] Microphone connected for lip sync');
                document.getElementById('mic-btn').textContent = 'Mic Active';
                document.getElementById('mic-btn').style.background = 'rgba(76, 175, 80, 0.3)';
            } catch (err) {
                console.error('[AvatarTest] Microphone access failed:', err);
                alert('Could not access microphone: ' + err.message);
            }
        });

        document.getElementById('mic-stop-btn').addEventListener('click', () => {
            if (this.micStream) {
                this.micStream.getTracks().forEach(t => t.stop());
                this.micStream = null;
            }
            this.stopLipSync();
            this.setParam('mouthOpen', 0);
            document.getElementById('mic-btn').textContent = 'Use Microphone';
            document.getElementById('mic-btn').style.background = '';
            console.log('[AvatarTest] Microphone disconnected');
        });

        this.testAudio.addEventListener('ended', () => {
            this.stopLipSync();
            this.setParam('mouthOpen', 0);
        });

        // Sensitivity
        document.getElementById('sensitivity').addEventListener('input', (e) => {
            this.sensitivity = parseFloat(e.target.value);
            document.getElementById('sensitivity-val').textContent = this.sensitivity.toFixed(1);
        });

        // List parameters
        document.getElementById('list-params-btn').addEventListener('click', () => {
            document.getElementById('param-list').textContent = this.listParameters();
        });

        // List parts
        document.getElementById('list-parts-btn').addEventListener('click', () => {
            document.getElementById('parts-list').textContent = this.listParts();
        });

        // === Action System Controls ===
        this.setupActionControls();
    }

    setupActionControls() {
        // Initialize action system if available
        if (typeof ActionParser !== 'undefined' &&
            typeof ActionLibrary !== 'undefined' &&
            typeof ActionExecutor !== 'undefined') {

            this.actionParser = new ActionParser();
            this.actionLibrary = new ActionLibrary();
            this.actionExecutor = new ActionExecutor(
                this.actionLibrary,
                (param, value) => this.setParam(param, value),
                (partId, opacity) => {
                    // Disable pose system when manually controlling parts
                    // Pose system controls arm part switching and fights with manual opacity
                    if (this.model?.internalModel?.pose) {
                        this._poseDisabledByGesture = true;
                        this.model.internalModel.pose = null;
                    }
                    this.setPartOpacity(partId, opacity);
                }
            );

            // Start the executor
            this.actionExecutor.start();
            console.log('[AvatarTest] Action system initialized');

            // Mood buttons
            document.querySelectorAll('[data-mood]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const mood = btn.dataset.mood;
                    this.actionExecutor.setMood(mood);
                    console.log(`[AvatarTest] Mood set: ${mood}`);
                });
            });

            // Gesture buttons
            document.querySelectorAll('[data-gesture]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const gesture = btn.dataset.gesture;
                    this.actionExecutor.playGesture(gesture);
                    console.log(`[AvatarTest] Gesture played: ${gesture}`);
                });
            });

            // Parse & Execute button
            document.getElementById('parse-action-btn')?.addEventListener('click', () => {
                const input = document.getElementById('action-input').value;
                const result = this.actionParser.parse(input);

                // Display result
                const resultEl = document.getElementById('action-result');
                resultEl.textContent = `Clean: "${result.cleanText}"\nActions: ${JSON.stringify(result.actions, null, 1)}`;

                // Execute actions
                if (result.actions.length > 0) {
                    this.actionExecutor.executeActions(result.actions);
                }
            });

            // Reset Arms button
            document.getElementById('reset-arms-btn')?.addEventListener('click', () => {
                this.restorePoseControl();
                console.log('[AvatarTest] Arms reset to model control');
            });

            // Clear Mood button - allows manual slider control
            document.getElementById('clear-mood-btn')?.addEventListener('click', () => {
                this.actionExecutor.clearMood();
                console.log('[AvatarTest] Mood cleared - sliders now control parameters');
            });

        } else {
            console.warn('[AvatarTest] Action system not available');
        }
    }
}

// Start when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.avatarTest = new AvatarTest();
    window.avatarTest.init();
});
