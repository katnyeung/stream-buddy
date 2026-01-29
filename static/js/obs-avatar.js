/**
 * OBS Avatar Controller - Minimal VTuber renderer for OBS browser source
 *
 * Features:
 * - Fixed 1920x1080 transparent canvas
 * - Position/movement system with zones (left, center, right)
 * - Zoom control
 * - Rotation (body orientation)
 * - WebSocket connection for server commands
 * - Overlay layer support (future-ready)
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

// Movement step sizes (pixels for 1920x1080 canvas)
const MOVE_STEP = {
    x: 150,  // ~8% of 1920
    y: 65    // ~6% of 1080
};

// Position bounds (pixels for 1920x1080 canvas)
// Extended to allow avatar to go partially off-screen (-20% to 120%)
const POSITION_BOUNDS = {
    minX: -384,   // -20% (allows half body from left)
    maxX: 2304,   // 120% (allows half body from right)
    minY: -216,   // -20% (allows partial top)
    maxY: 1296    // 120% (allows partial bottom)
};

// Zoom levels
const ZOOM_LEVELS = {
    normal: 0.4,
    in: 0.6,
    out: 0.3
};

// Body orientation presets (renamed from "rotate")
const BODY_ORIENTATIONS = {
    front: { angleX: 0, bodyAngleX: 0 },
    left: { angleX: -20, bodyAngleX: -10 },
    right: { angleX: 20, bodyAngleX: 10 }
};

// Easing functions
const EASING = {
    easeInOut: t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
    easeOut: t => 1 - Math.pow(1 - t, 3),
    easeIn: t => t * t * t
};

class OBSAvatar {
    constructor() {
        this.app = null;
        this.model = null;

        // PIXI containers (layers)
        this.layers = {
            background: null,
            avatar: null,
            overlays: null,
            ui: null
        };

        // Overlay manager
        this.overlayManager = null;

        // Position state
        this.position = {
            x: 960,           // Current X position (pixels)
            y: 810,           // Current Y position (pixels)
            scale: 0.4,       // Current scale
            facing: 'right',  // 'left' or 'right'
            bodyOrientation: 'front' // Body orientation: 'front', 'left', 'right'
        };

        // Animation state
        this.animation = {
            active: false,
            startTime: 0,
            duration: 0,
            startX: 0,
            targetX: 0,
            startY: 0,
            targetY: 0,
            startScale: 0,
            targetScale: 0,
            startFacing: 'right',
            targetFacing: 'right',
            walkCycle: 0,
            type: null  // 'move', 'zoom', 'rotate'
        };

        // Manual parameter values
        this.manualParams = {};

        // Rotation parameters (persisted separately)
        this.rotationParams = { angleX: 0, bodyAngleX: 0 };

        // Action system
        this.actionParser = null;
        this.actionLibrary = null;
        this.actionExecutor = null;

        // WebSocket
        this.ws = null;
        this.wsConnected = false;
        this.avatarId = 'buddy';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;

        // TTS audio for server-triggered speech
        this.ttsAudio = null;
        this.ttsAudioContext = null;
        this.ttsAnalyser = null;
        this.ttsDataArray = null;
        this.ttsAudioConnected = false;
        this.ttsLipSyncActive = false;
        this.ttsSmoothedVolume = 0;
        this.ttsOnEndCallback = null;  // Callback when TTS audio ends

        // Original model components (for mode switching)
        this._originalPhysics = null;
        this._originalPose = null;
        this._originalEyeBlink = null;
        this._originalBreath = null;

        // Dragging state
        this.isDragging = false;
        this.dragOffset = { x: 0, y: 0 };
    }

    async init() {
        console.log('[OBSAvatar] Initializing...');

        try {
            // Check dependencies
            if (typeof PIXI === 'undefined') {
                throw new Error('PIXI.js not loaded');
            }
            if (typeof PIXI.live2d === 'undefined') {
                throw new Error('pixi-live2d-display not loaded');
            }

            // Create PIXI app with fixed 1080p canvas
            const canvas = document.getElementById('obs-canvas');

            this.app = new PIXI.Application({
                view: canvas,
                width: 1920,
                height: 1080,
                backgroundColor: 0x000000,
                backgroundAlpha: 0,  // Fully transparent
                resolution: 1,
                autoDensity: false
            });

            // Create layer containers
            this.layers.background = new PIXI.Container();
            this.layers.avatar = new PIXI.Container();
            this.layers.overlays = new PIXI.Container();
            this.layers.ui = new PIXI.Container();

            this.app.stage.addChild(this.layers.background);
            this.app.stage.addChild(this.layers.avatar);
            this.app.stage.addChild(this.layers.overlays);
            this.app.stage.addChild(this.layers.ui);

            // Initialize overlay manager
            if (typeof OverlayManager !== 'undefined') {
                this.overlayManager = new OverlayManager(this.layers.overlays, 1920, 1080);
                console.log('[OBSAvatar] Overlay manager initialized');
            }

            // Initialize action system
            this.setupActionSystem();

            // Load default model
            await this.loadModel();

            // Don't auto-connect - wait for obs-app.js to start session
            // this.connectServer();

            // Setup dragging
            this.setupDragging();

            // Start render loop
            this.app.ticker.add(() => this.update());

            console.log('[OBSAvatar] Initialized successfully (waiting for session)');

        } catch (err) {
            console.error('[OBSAvatar] Init failed:', err);
        }
    }

    async loadModel(url = null) {
        // Default model URL - can be overridden by server
        const modelUrl = url || 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/haru/haru_greeter_t03.model3.json';

        console.log('[OBSAvatar] Loading model:', modelUrl);

        // Remove existing model
        if (this.model) {
            this.layers.avatar.removeChild(this.model);
            this.model.destroy();
            this.model = null;
        }

        try {
            const { Live2DModel } = PIXI.live2d;
            this.model = await Live2DModel.from(modelUrl, { autoInteract: false });

            // Store original components
            const internalModel = this.model.internalModel;
            this._originalPhysics = internalModel.physics;
            this._originalPose = internalModel.pose;
            this._originalEyeBlink = internalModel.eyeBlink;
            this._originalBreath = internalModel.breath;

            // Use STRICT mode - disable ALL Live2D internals
            // Server sends idle behaviors via Redis, browser just executes smoothly
            this.setServerStrictMode(true);
            console.log('[OBSAvatar] Strict mode enabled - server controls all behavior');

            // Position model
            this.applyPosition();

            // Add to avatar layer
            this.layers.avatar.addChild(this.model);

            console.log('[OBSAvatar] Model loaded successfully');
            window.model = this.model;  // Debug access

        } catch (err) {
            console.error('[OBSAvatar] Model load failed:', err);
        }
    }

    setupActionSystem() {
        if (typeof ActionParser !== 'undefined' &&
            typeof ActionLibrary !== 'undefined' &&
            typeof ActionExecutor !== 'undefined') {

            this.actionParser = new ActionParser();
            this.actionLibrary = new ActionLibrary();
            this.actionExecutor = new ActionExecutor(
                this.actionLibrary,
                (param, value) => this.setParam(param, value),
                (partId, opacity) => this.setPartOpacity(partId, opacity)
            );

            // Hook into navigation triggers
            this.actionExecutor.onNavigationTrigger = (direction) => {
                console.log(`[OBSAvatar] Navigation trigger from gesture: ${direction}`);
                this.sendToServer({
                    type: 'navigation_trigger',
                    direction: direction
                });
            };

            // Exclude mouthOpen from action executor (controlled by lip sync)
            this.actionExecutor.excludeParam('mouthOpen');

            this.actionExecutor.start();
            console.log('[OBSAvatar] Action system initialized (mouthOpen excluded)');
        } else {
            console.warn('[OBSAvatar] Action system not available');
        }
    }

    setupDragging() {
        const canvas = this.app.view;

        canvas.addEventListener('mousedown', (e) => {
            if (!this.model) return;

            // Check if click is on the model (rough hit test)
            const rect = canvas.getBoundingClientRect();
            const scaleX = 1920 / rect.width;
            const scaleY = 1080 / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;

            // Simple bounding box check - covers full avatar from head to bottom
            const modelBounds = {
                left: this.position.x - 350 * this.position.scale,
                right: this.position.x + 350 * this.position.scale,
                top: this.position.y - 900 * this.position.scale,  // Extended to cover head/upper body
                bottom: this.position.y + 400 * this.position.scale
            };

            if (mouseX >= modelBounds.left && mouseX <= modelBounds.right &&
                mouseY >= modelBounds.top && mouseY <= modelBounds.bottom) {
                this.isDragging = true;
                this.dragOffset.x = mouseX - this.position.x;
                this.dragOffset.y = mouseY - this.position.y;
                canvas.style.cursor = 'grabbing';
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            if (!this.isDragging || !this.model) return;

            const rect = canvas.getBoundingClientRect();
            const scaleX = 1920 / rect.width;
            const scaleY = 1080 / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;

            // Calculate new position with bounds
            const newX = Math.max(POSITION_BOUNDS.minX, Math.min(POSITION_BOUNDS.maxX, mouseX - this.dragOffset.x));
            const newY = Math.max(POSITION_BOUNDS.minY, Math.min(POSITION_BOUNDS.maxY, mouseY - this.dragOffset.y));

            this.position.x = newX;
            this.position.y = newY;
            this.applyPosition();
        });

        canvas.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                canvas.style.cursor = 'default';

                // Send position update to server for sync
                this.sendToServer({
                    type: 'position_update',
                    x: this.position.x,
                    y: this.position.y
                });

                console.log(`[OBSAvatar] Dragged to (${Math.round(this.position.x)}, ${Math.round(this.position.y)})`);
            }
        });

        canvas.addEventListener('mouseleave', () => {
            if (this.isDragging) {
                this.isDragging = false;
                canvas.style.cursor = 'default';
            }
        });

        // Change cursor on hover over model
        canvas.addEventListener('mousemove', (e) => {
            if (this.isDragging || !this.model) return;

            const rect = canvas.getBoundingClientRect();
            const scaleX = 1920 / rect.width;
            const scaleY = 1080 / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;

            const modelBounds = {
                left: this.position.x - 350 * this.position.scale,
                right: this.position.x + 350 * this.position.scale,
                top: this.position.y - 900 * this.position.scale,  // Extended to cover head/upper body
                bottom: this.position.y + 400 * this.position.scale
            };

            if (mouseX >= modelBounds.left && mouseX <= modelBounds.right &&
                mouseY >= modelBounds.top && mouseY <= modelBounds.bottom) {
                canvas.style.cursor = 'grab';
            } else {
                canvas.style.cursor = 'default';
            }
        });

        // Scroll wheel to zoom
        canvas.addEventListener('wheel', (e) => {
            if (!this.model) return;

            e.preventDefault();

            const zoomDelta = e.deltaY > 0 ? -0.02 : 0.02;
            const newScale = Math.max(0.2, Math.min(0.8, this.position.scale + zoomDelta));

            this.position.scale = newScale;
            this.applyPosition();

            // Send position update to server
            this.sendToServer({
                type: 'position_update',
                x: this.position.x,
                y: this.position.y,
                scale: this.position.scale
            });
        }, { passive: false });

        console.log('[OBSAvatar] Dragging and zoom enabled');
    }

    // === Position/Movement System ===

    applyPosition() {
        if (!this.model) return;

        this.model.anchor.set(0.5, 0.5);
        this.model.x = this.position.x;
        this.model.y = this.position.y;

        // Apply scale with facing direction
        const scaleX = this.position.facing === 'left' ? -this.position.scale : this.position.scale;
        this.model.scale.set(scaleX, this.position.scale);
    }

    /**
     * Move in a direction (accumulative)
     * @param {string} direction - 'up', 'down', 'left', 'right'
     * @param {number} duration - Animation duration in ms
     */
    move(direction, duration = 400) {
        let targetX = this.position.x;
        let targetY = this.position.y;

        switch (direction) {
            case 'left':
                targetX = Math.max(POSITION_BOUNDS.minX, this.position.x - MOVE_STEP.x);
                break;
            case 'right':
                targetX = Math.min(POSITION_BOUNDS.maxX, this.position.x + MOVE_STEP.x);
                break;
            case 'up':
                targetY = Math.max(POSITION_BOUNDS.minY, this.position.y - MOVE_STEP.y);
                break;
            case 'down':
                targetY = Math.min(POSITION_BOUNDS.maxY, this.position.y + MOVE_STEP.y);
                break;
            default:
                console.warn('[OBSAvatar] Unknown direction:', direction);
                return;
        }

        // Determine facing based on horizontal movement
        const targetFacing = direction === 'left' ? 'left' :
                            direction === 'right' ? 'right' :
                            this.position.facing;

        this.animation = {
            active: true,
            startTime: performance.now(),
            duration: duration,
            startX: this.position.x,
            targetX: targetX,
            startY: this.position.y,
            targetY: targetY,
            startScale: this.position.scale,
            targetScale: this.position.scale,
            startFacing: this.position.facing,
            targetFacing: targetFacing,
            walkCycle: 0,
            type: 'move'
        };

        console.log(`[OBSAvatar] Moving ${direction} to (${targetX}, ${targetY})`);
    }

    /**
     * Move to absolute position
     */
    moveTo(x, y, duration = 600) {
        const targetX = Math.max(POSITION_BOUNDS.minX, Math.min(POSITION_BOUNDS.maxX, x));
        const targetY = Math.max(POSITION_BOUNDS.minY, Math.min(POSITION_BOUNDS.maxY, y));

        const targetFacing = targetX < this.position.x ? 'left' :
                            targetX > this.position.x ? 'right' :
                            this.position.facing;

        this.animation = {
            active: true,
            startTime: performance.now(),
            duration: duration,
            startX: this.position.x,
            targetX: targetX,
            startY: this.position.y,
            targetY: targetY,
            startScale: this.position.scale,
            targetScale: this.position.scale,
            startFacing: this.position.facing,
            targetFacing: targetFacing,
            walkCycle: 0,
            type: 'move'
        };

        console.log(`[OBSAvatar] Moving to (${targetX}, ${targetY})`);
    }

    /**
     * Reset to center position
     */
    resetPosition(duration = 600) {
        this.moveTo(960, 810, duration);
        console.log('[OBSAvatar] Reset to center');
    }

    /**
     * Zoom in/out
     */
    zoom(level, duration = 800) {
        const targetScale = ZOOM_LEVELS[level];
        if (targetScale === undefined) {
            console.warn('[OBSAvatar] Unknown zoom level:', level);
            return;
        }

        this.animation = {
            active: true,
            startTime: performance.now(),
            duration: duration,
            startX: this.position.x,
            targetX: this.position.x,
            startY: this.position.y,
            targetY: this.position.y,
            startScale: this.position.scale,
            targetScale: targetScale,
            startFacing: this.position.facing,
            targetFacing: this.position.facing,
            walkCycle: 0,
            type: 'zoom'
        };

        console.log(`[OBSAvatar] Zooming to ${level} (scale: ${targetScale})`);
    }

    /**
     * Set body orientation (renamed from rotate)
     */
    setBodyOrientation(direction) {
        const target = BODY_ORIENTATIONS[direction];
        if (!target) {
            console.warn('[OBSAvatar] Unknown body orientation:', direction);
            return;
        }

        this.position.bodyOrientation = direction;
        this.rotationParams = { ...target };

        // Apply via parameters
        this.setParam('angleX', target.angleX);
        this.setParam('bodyAngleX', target.bodyAngleX);

        console.log(`[OBSAvatar] Body orientation: ${direction}`);
    }

    /**
     * Update animation each frame
     */
    updateAnimation() {
        if (!this.animation.active) return;

        const now = performance.now();
        const elapsed = now - this.animation.startTime;
        const progress = Math.min(elapsed / this.animation.duration, 1);
        const eased = EASING.easeInOut(progress);

        // Interpolate position
        this.position.x = this.animation.startX + (this.animation.targetX - this.animation.startX) * eased;
        this.position.y = this.animation.startY + (this.animation.targetY - this.animation.startY) * eased;
        this.position.scale = this.animation.startScale + (this.animation.targetScale - this.animation.startScale) * eased;

        // Update facing at midpoint
        if (eased > 0.5) {
            this.position.facing = this.animation.targetFacing;
        }

        // Walking animation (body sway during move)
        if (this.animation.type === 'move' && progress < 1) {
            this.animation.walkCycle += 0.15;
            const walkSway = Math.sin(this.animation.walkCycle) * 3;
            this.setParam('bodyAngleX', walkSway);
        }

        // Apply position
        this.applyPosition();

        // Check if animation complete
        if (progress >= 1) {
            this.animation.active = false;

            // Reset walk sway
            if (this.animation.type === 'move') {
                this.setParam('bodyAngleX', this.rotationParams.bodyAngleX || 0);
            }

            // Send movement_complete to server
            this.sendToServer({
                type: 'movement_complete',
                zone: this.position.zone,
                x: this.position.x,
                facing: this.position.facing
            });

            console.log(`[OBSAvatar] Animation complete (${this.animation.type})`);
        }
    }

    // === Parameter Control ===

    setParam(key, value) {
        this.manualParams[key] = value;
        this.applyParam(key, value);
    }

    applyParam(key, value) {
        if (!this.model) return false;

        const coreModel = this.model.internalModel.coreModel;
        const aliases = PARAM_MAP[key] || [key];

        for (const name of aliases) {
            try {
                if (typeof coreModel.getParameterIndex === 'function') {
                    const idx = coreModel.getParameterIndex(name);
                    if (idx >= 0) {
                        coreModel.setParameterValueByIndex(idx, value);
                        return true;
                    }
                }
            } catch (e) {
                // Continue to next alias
            }
        }
        return false;
    }

    applyManualParams() {
        for (const [key, value] of Object.entries(this.manualParams)) {
            this.applyParam(key, value);
        }
    }

    setPartOpacity(partIdOrIndex, opacity) {
        if (!this.model) return false;

        const coreModel = this.model.internalModel.coreModel;

        try {
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
        } catch (e) {
            console.error('[OBSAvatar] Error setting part opacity:', e);
        }
        return false;
    }

    setServerStrictMode(strict) {
        if (!this.model) return;

        const internalModel = this.model.internalModel;

        if (strict) {
            // STRICT MODE: Disable ALL Live2D internals
            // Server sends idle behaviors (idle_sway, idle_breathe, blink) via Redis at 2fps
            // Browser executes them smoothly at 60fps via ActionExecutor
            if (internalModel.motionManager) {
                internalModel.motionManager.stopAllMotions();
                internalModel.motionManager.update = () => false;
            }
            if (internalModel.expressionManager) {
                internalModel.expressionManager.update = () => false;
            }
            // Disable ALL internal systems - server controls everything
            internalModel.physics = null;
            internalModel.pose = null;
            internalModel.eyeBlink = null;
            internalModel.breath = null;

            console.log('[OBSAvatar] Strict mode: All Live2D internals disabled');
        } else {
            // Hold mode - keep physics/breath/blink for local testing
            if (internalModel.motionManager) {
                internalModel.motionManager.stopAllMotions();
                internalModel.motionManager.update = () => false;
            }
            if (internalModel.expressionManager) {
                internalModel.expressionManager.update = () => false;
            }
            if (this._originalPhysics) internalModel.physics = this._originalPhysics;
            if (this._originalEyeBlink) internalModel.eyeBlink = this._originalEyeBlink;
            if (this._originalBreath) internalModel.breath = this._originalBreath;
            internalModel.pose = null;

            console.log('[OBSAvatar] Hold mode: Physics/breath/blink active');
        }
    }

    // === Update Loop ===

    update() {
        if (!this.model) return;

        // Update animation
        this.updateAnimation();

        // Apply manual params
        this.applyManualParams();
    }

    // === WebSocket Connection ===

    connectServer(avatarId = null) {
        // Try to get session ID from:
        // 1. Passed parameter
        // 2. URL query param (?session=xxx)
        // 3. localStorage (shared with main page)
        // 4. Default to 'buddy'
        const urlParams = new URLSearchParams(window.location.search);
        const urlSession = urlParams.get('session');
        const storedSession = localStorage.getItem('streambuddy_session_id');

        this.avatarId = avatarId || urlSession || storedSession || 'buddy';

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/avatar/${this.avatarId}`;

        console.log(`[OBSAvatar] Session ID: ${this.avatarId}`);
        console.log(`[OBSAvatar] Connecting to ${url}...`);
        this.ws = new WebSocket(url);

        // Watch for session ID changes in localStorage (when main page starts new session)
        this.startSessionWatcher();

        this.ws.onopen = () => {
            this.wsConnected = true;
            this.reconnectAttempts = 0;
            console.log('[OBSAvatar] WebSocket connected');

            // Start idle engine - server will send idle behaviors via Redis
            this.sendToServer({ type: 'start_idle' });
            console.log('[OBSAvatar] Sent start_idle to server');
        };

        this.ws.onclose = () => {
            this.wsConnected = false;
            console.log('[OBSAvatar] WebSocket disconnected');
            this.scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('[OBSAvatar] WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            try {
                const cmd = JSON.parse(event.data);
                this.handleServerCommand(cmd);
            } catch (e) {
                console.warn('[OBSAvatar] Invalid server message:', e);
            }
        };
    }

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[OBSAvatar] Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        console.log(`[OBSAvatar] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => this.connectServer(this.avatarId), delay);
    }

    startSessionWatcher() {
        // Watch for session changes in localStorage
        // When main page starts a new session, reconnect to that session
        this._sessionWatchInterval = setInterval(() => {
            const currentSession = localStorage.getItem('streambuddy_session_id');
            if (currentSession && currentSession !== this.avatarId) {
                console.log(`[OBSAvatar] Session changed: ${this.avatarId} -> ${currentSession}`);
                this.avatarId = currentSession;

                // Reconnect to new session
                if (this.ws) {
                    this.ws.close();
                }
                this.reconnectAttempts = 0;
                this.connectServer(currentSession);
            }
        }, 2000);  // Check every 2 seconds
    }

    stopSessionWatcher() {
        if (this._sessionWatchInterval) {
            clearInterval(this._sessionWatchInterval);
            this._sessionWatchInterval = null;
        }
    }

    sendToServer(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    handleServerCommand(cmd) {
        // Log non-idle commands
        const quietTypes = ['gesture'];
        const quietGestures = ['idle_sway', 'idle_breathe', 'blink'];
        const isQuiet = quietTypes.includes(cmd.type) && quietGestures.includes(cmd.name);
        if (!isQuiet) {
            console.log(`[OBSAvatar] Command: ${cmd.type}`, cmd);
        }

        switch (cmd.type) {
            case 'init':
                if (cmd.state) this.handleStateCommand(cmd.state);
                if (cmd.mood) this.handleMoodCommand(cmd.mood, 1.0);
                if (cmd.position) {
                    this.handlePositionSync(cmd.position);
                    console.log('[OBSAvatar] Initial position synced from server');
                }
                break;

            case 'state':
                this.handleStateCommand(cmd.value);
                break;

            case 'mood':
                this.handleMoodCommand(cmd.name, cmd.intensity || 1.0);
                break;

            case 'gesture':
                this.handleGestureCommand(cmd.name, cmd.intensity || 1.0);
                break;

            case 'action':
                this.handleActionCommand(cmd.name, cmd.params || {});
                break;

            case 'speech':
                this.handleSpeechCommand(cmd.text, cmd.audio_base64);
                break;

            case 'move':
                this.handleMoveCommand(cmd);
                break;

            case 'move_to':
                this.handleMoveToCommand(cmd);
                break;

            case 'zoom':
                this.handleZoomCommand(cmd);
                break;

            case 'body':
                this.handleBodyCommand(cmd);
                break;

            case 'load_model':
                this.loadModel(cmd.url);
                break;

            case 'position_sync':
                // Sync position from another client (control panel <-> overlay)
                this.handlePositionSync(cmd);
                break;

            case 'idle_started':
                console.log('[OBSAvatar] Idle engine started');
                break;

            case 'idle_stopped':
                console.log('[OBSAvatar] Idle engine stopped');
                break;

            case 'overlay':
                this.handleOverlayCommand(cmd);
                break;

            case 'overlay_hide':
                this.handleOverlayHide(cmd);
                break;

            default:
                console.warn(`[OBSAvatar] Unknown command type: ${cmd.type}`);
        }
    }

    handleOverlayCommand(cmd) {
        if (!this.overlayManager) {
            console.warn('[OBSAvatar] Overlay manager not available');
            return;
        }

        const id = cmd.id || `overlay_${Date.now()}`;
        const overlayType = cmd.overlay_type || 'text';
        const options = {
            ...cmd.options,
            animateIn: cmd.animate_in || 'fade'
        };

        this.overlayManager.show(id, overlayType, options);
    }

    handleOverlayHide(cmd) {
        if (!this.overlayManager) return;

        if (cmd.id) {
            this.overlayManager.hide(cmd.id, cmd.animate_out || 'fade');
        } else if (cmd.all) {
            this.overlayManager.hideAll();
        }
    }

    handleStateCommand(state) {
        console.log(`[OBSAvatar] State: ${state}`);
        // State handling if needed
    }

    handleMoodCommand(mood, intensity = 1.0) {
        if (this.actionExecutor) {
            this.actionExecutor.setMood(mood, { intensity });
        }
    }

    handleGestureCommand(gesture, intensity = 1.0) {
        if (this.actionExecutor) {
            this.actionExecutor.playGesture(gesture, { intensity });
        }
    }

    handleActionCommand(action, params = {}) {
        if (this.actionExecutor) {
            this.actionExecutor.executeAction(action, params);
        }
    }

    handleMoveCommand(cmd) {
        const direction = cmd.direction;
        const duration = cmd.duration || 400;
        this.move(direction, duration);
    }

    handleMoveToCommand(cmd) {
        // Convert from ratio (0-1) to pixels if needed
        let x = cmd.x;
        let y = cmd.y;
        if (x <= 1) x = x * 1920;  // Convert ratio to pixels
        if (y <= 1) y = y * 1080;
        const duration = cmd.duration || 600;
        this.moveTo(x, y, duration);
    }

    handleZoomCommand(cmd) {
        const level = cmd.level || cmd.name || 'normal';
        const duration = cmd.duration || 800;
        this.zoom(level, duration);
    }

    handleBodyCommand(cmd) {
        const direction = cmd.direction || 'front';
        this.setBodyOrientation(direction);
    }

    handlePositionSync(positionData) {
        // Sync position state from server (for reconnection or cross-client sync)
        // Skip if we're currently dragging (we're the source)
        if (this.isDragging) return;

        let changed = false;

        if (positionData.x !== undefined && Math.abs(this.position.x - positionData.x) > 1) {
            this.position.x = parseFloat(positionData.x);
            changed = true;
        }
        if (positionData.y !== undefined && Math.abs(this.position.y - positionData.y) > 1) {
            this.position.y = parseFloat(positionData.y);
            changed = true;
        }
        if (positionData.scale !== undefined && Math.abs(this.position.scale - positionData.scale) > 0.01) {
            this.position.scale = parseFloat(positionData.scale);
            changed = true;
        }
        if (positionData.facing !== undefined) {
            this.position.facing = positionData.facing;
        }
        if (positionData.bodyOrientation !== undefined) {
            this.position.bodyOrientation = positionData.bodyOrientation;
        }

        if (changed) {
            this.applyPosition();
            console.log('[OBSAvatar] Position synced from server:', this.position);
        }
    }

    handleSpeechCommand(text, audioBase64) {
        console.log(`[OBSAvatar] Speech command received: "${text?.substring(0, 50)}..."`);
        console.log(`[OBSAvatar] Audio data present: ${audioBase64 ? 'yes (' + audioBase64.length + ' chars)' : 'NO'}`);

        if (audioBase64) {
            this.playTTSAudio(audioBase64);
        } else {
            console.warn('[OBSAvatar] No audio data in speech command!');
        }
    }

    // === TTS Audio ===

    /**
     * Play TTS audio with lip sync
     * @param {string} audioBase64 - Base64 encoded audio
     * @param {Function} onEnd - Optional callback when audio ends
     */
    playTTSAudio(audioBase64, onEnd = null) {
        console.log(`[OBSAvatar] playTTSAudio called, audio length: ${audioBase64?.length || 0}`);

        if (!this.ttsAudio) {
            console.log('[OBSAvatar] Creating new Audio element');
            this.ttsAudio = new Audio();

            if (!this.ttsAudioContext) {
                console.log('[OBSAvatar] Creating AudioContext for lip sync');
                this.ttsAudioContext = new (window.AudioContext || window.webkitAudioContext)();
                this.ttsAnalyser = this.ttsAudioContext.createAnalyser();
                this.ttsAnalyser.fftSize = 256;
                this.ttsAnalyser.smoothingTimeConstant = 0.5;
                this.ttsDataArray = new Uint8Array(this.ttsAnalyser.frequencyBinCount);
            }
        }

        // Store callback
        this.ttsOnEndCallback = onEnd;

        if (!this.ttsAudio.paused) {
            console.log('[OBSAvatar] Stopping previous audio');
            this.ttsAudio.pause();
            this.ttsAudio.currentTime = 0;
        }

        console.log('[OBSAvatar] Setting audio source...');
        this.ttsAudio.src = `data:audio/mp3;base64,${audioBase64}`;

        if (!this.ttsAudioConnected) {
            try {
                const source = this.ttsAudioContext.createMediaElementSource(this.ttsAudio);
                source.connect(this.ttsAnalyser);
                this.ttsAnalyser.connect(this.ttsAudioContext.destination);
                this.ttsAudioConnected = true;
            } catch (e) {
                console.warn('[OBSAvatar] Audio connection error:', e.message);
            }
        }

        if (this.ttsAudioContext.state === 'suspended') {
            this.ttsAudioContext.resume();
        }

        this.startTTSLipSync();

        console.log('[OBSAvatar] Starting audio playback...');
        this.ttsAudio.play().then(() => {
            console.log('[OBSAvatar] Audio playback started successfully');
        }).catch(e => {
            console.error('[OBSAvatar] Audio playback FAILED:', e.message || e);
            // Call callback on error too
            if (this.ttsOnEndCallback) {
                this.ttsOnEndCallback();
                this.ttsOnEndCallback = null;
            }
        });

        this.ttsAudio.onended = () => {
            console.log('[OBSAvatar] Audio playback ended');
            this.stopTTSLipSync();

            // Call the callback if provided
            if (this.ttsOnEndCallback) {
                this.ttsOnEndCallback();
                this.ttsOnEndCallback = null;
            } else {
                // Only send ready if no callback (not using queue)
                this.sendToServer({ type: 'ready' });
            }
        };
    }

    startTTSLipSync() {
        if (this.ttsLipSyncActive) return;
        this.ttsLipSyncActive = true;

        const animateLipSync = () => {
            if (!this.ttsLipSyncActive) return;

            this.ttsAnalyser.getByteFrequencyData(this.ttsDataArray);

            let sum = 0;
            for (let i = 2; i < 20; i++) {
                sum += this.ttsDataArray[i];
            }
            const avg = sum / 18 / 255;
            const smoothed = this.ttsSmoothedVolume * 0.3 + avg * 0.7;
            this.ttsSmoothedVolume = smoothed;

            const mouthOpen = Math.min(1, Math.pow(smoothed, 0.7) * 1.5);
            this.setParam('mouthOpen', mouthOpen);
            this.sendToServer({ type: 'lipsync', amplitude: mouthOpen });

            requestAnimationFrame(animateLipSync);
        };

        this.ttsSmoothedVolume = 0;
        animateLipSync();
    }

    stopTTSLipSync() {
        this.ttsLipSyncActive = false;
        this.setParam('mouthOpen', 0);
        this.sendToServer({ type: 'lipsync', amplitude: 0 });
    }

    // === Public API ===

    getPosition() {
        return { ...this.position };
    }

    getZones() {
        return { ...ZONES };
    }

    getZoomLevels() {
        return { ...ZOOM_LEVELS };
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.obsAvatar = new OBSAvatar();
    window.obsAvatar.init().then(() => {
        // Check if we're in standalone overlay mode (no obs-app.js controlling us)
        // In this case, auto-connect to the session
        const isOverlayPage = window.location.pathname.includes('/obs/overlay');
        const urlParams = new URLSearchParams(window.location.search);
        const hasSessionParam = urlParams.has('session');
        const hasStoredSession = localStorage.getItem('streambuddy_session_id');

        if (isOverlayPage || (hasSessionParam && !window.obsStreamBuddy)) {
            // Auto-connect in overlay mode
            const sessionId = urlParams.get('session') || hasStoredSession || 'buddy';
            console.log(`[OBSAvatar] Standalone mode - auto-connecting to session: ${sessionId}`);

            // Wait a bit for model to fully load
            setTimeout(() => {
                if (window.obsAvatar && window.obsAvatar.model) {
                    window.obsAvatar.connectServer(sessionId);
                }
            }, 500);
        }
    });
});
