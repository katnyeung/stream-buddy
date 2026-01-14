/**
 * AvatarManager - Facade class that combines all avatar functionality
 * Provides a simple API for the main Stream Buddy application
 */

class AvatarManager {
    constructor(canvasId, options = {}) {
        this.canvasId = canvasId;
        this.options = {
            modelPath: options.modelPath || null,
            scale: options.scale || 0.35,
            backgroundColor: options.backgroundColor || 0x1a1a2e,
            backgroundAlpha: options.backgroundAlpha || 0,
            ...options
        };

        // PIXI app and model
        this.app = null;
        this.model = null;

        // Components
        this.controller = null;
        this.audioAnalyzer = null;
        this.emotionDetector = null;
        this.stateMachine = null;

        // State
        this.isInitialized = false;
        this.isLipSyncActive = false;
        this.currentAudio = null;

        // Control mode (for disabling model's internal systems)
        this.controlMode = 'hold'; // 'strict', 'hold', 'auto'
        this._originalPhysics = null;
        this._originalPose = null;
        this._originalEyeBlink = null;
        this._originalBreath = null;
        this._originalMotionManagerUpdate = null;
        this._poseDisabledByGesture = false;

        // Callbacks
        this.onReady = options.onReady || null;
        this.onError = options.onError || null;
    }

    /**
     * Initialize the avatar system
     */
    async init() {
        if (this.isInitialized) return this;

        try {
            // Initialize PIXI
            await this._initPixi();

            // Initialize audio analyzer
            this.audioAnalyzer = new AudioAnalyzer();
            await this.audioAnalyzer.init();

            // Initialize emotion detector
            this.emotionDetector = new EmotionDetector();

            console.log('[AvatarManager] Initialized (waiting for model)');
            return this;

        } catch (error) {
            console.error('[AvatarManager] Initialization failed:', error);
            if (this.onError) this.onError(error);
            throw error;
        }
    }

    /**
     * Initialize PIXI application
     */
    async _initPixi() {
        const canvas = document.getElementById(this.canvasId);
        if (!canvas) {
            throw new Error(`Canvas element #${this.canvasId} not found`);
        }

        const container = canvas.parentElement;

        // Make PIXI available globally for pixi-live2d-display
        window.PIXI = PIXI;

        // PIXI v6 API
        this.app = new PIXI.Application({
            view: canvas,
            width: container.clientWidth,
            height: container.clientHeight,
            backgroundColor: this.options.backgroundColor,
            backgroundAlpha: this.options.backgroundAlpha,
            resolution: window.devicePixelRatio || 1,
            autoDensity: true,
        });

        // Handle resize
        window.addEventListener('resize', () => this._handleResize());
    }

    /**
     * Load a Live2D model
     */
    async loadModel(modelPath) {
        if (!this.app) {
            await this.init();
        }

        // Remove existing model
        if (this.model) {
            this.app.stage.removeChild(this.model);
            this.model.destroy();
            this.model = null;
            this.controller = null;
        }

        try {
            const { Live2DModel } = PIXI.live2d;

            this.model = await Live2DModel.from(modelPath, {
                autoInteract: false,
                autoUpdate: true
            });

            // Position and scale
            this._positionModel();

            // Add to stage
            this.app.stage.addChild(this.model);

            // Store original internal model components for mode switching
            const internalModel = this.model.internalModel;
            this._originalPhysics = internalModel.physics;
            this._originalPose = internalModel.pose;
            this._originalEyeBlink = internalModel.eyeBlink;
            this._originalBreath = internalModel.breath;
            if (internalModel.motionManager) {
                this._originalMotionManagerUpdate = internalModel.motionManager.update?.bind(internalModel.motionManager);
            }

            // Initialize controller
            this.controller = new AvatarController(this.model);

            // Initialize state machine
            this.stateMachine = new AvatarStateMachine(
                this.controller,
                this.emotionDetector
            );
            this.stateMachine.start();

            // Apply hold+auto mode (disable idle motion, keep physics/breathing/blink)
            this._applyControlMode();

            // Setup zoom/drag controls
            this.setupViewControls();

            this.isInitialized = true;
            console.log('[AvatarManager] Model loaded:', modelPath);

            if (this.onReady) this.onReady();
            return this;

        } catch (error) {
            console.error('[AvatarManager] Failed to load model:', error);
            if (this.onError) this.onError(error);
            throw error;
        }
    }

    /**
     * Position and scale the model
     */
    _positionModel() {
        if (!this.model || !this.app) return;

        const container = this.app.view.parentElement;
        const width = container.clientWidth;
        const height = container.clientHeight;

        // Scale to fit container
        const scale = Math.min(width / 1000, height / 1000) * this.options.scale;
        this.model.scale.set(scale);

        // Center horizontally, position lower vertically
        this.model.anchor.set(0.5, 0.5);
        this.model.x = width / 2;
        this.model.y = height / 2 + height * 0.12;
    }

    /**
     * Handle window resize
     */
    _handleResize() {
        if (!this.app) return;

        const container = this.app.view.parentElement;
        this.app.renderer.resize(container.clientWidth, container.clientHeight);
        this._positionModel();
        this._applyViewTransform();
    }

    /**
     * Setup zoom and drag controls
     */
    setupViewControls() {
        // View transform state
        this.viewZoom = 1;
        this.viewOffsetX = 0;
        this.viewOffsetY = 0;
        this._isDragging = false;
        this._dragStartX = 0;
        this._dragStartY = 0;
        this._dragStartOffsetX = 0;
        this._dragStartOffsetY = 0;

        const container = document.getElementById('avatar-container');
        if (!container) return;

        // Zoom buttons
        const zoomInBtn = document.getElementById('avatar-zoom-in');
        const zoomOutBtn = document.getElementById('avatar-zoom-out');
        const resetBtn = document.getElementById('avatar-reset');

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => this.zoomIn());
        }
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => this.zoomOut());
        }
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.resetView());
        }

        // Mouse wheel zoom
        container.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                this.zoomIn(0.1);
            } else {
                this.zoomOut(0.1);
            }
        }, { passive: false });

        // Drag to pan
        container.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return; // Left click only
            this._isDragging = true;
            this._dragStartX = e.clientX;
            this._dragStartY = e.clientY;
            this._dragStartOffsetX = this.viewOffsetX;
            this._dragStartOffsetY = this.viewOffsetY;
            container.classList.add('dragging');
        });

        document.addEventListener('mousemove', (e) => {
            if (!this._isDragging) return;
            const dx = e.clientX - this._dragStartX;
            const dy = e.clientY - this._dragStartY;
            this.viewOffsetX = this._dragStartOffsetX + dx;
            this.viewOffsetY = this._dragStartOffsetY + dy;
            this._applyViewTransform();
        });

        document.addEventListener('mouseup', () => {
            if (this._isDragging) {
                this._isDragging = false;
                container.classList.remove('dragging');
            }
        });

        console.log('[AvatarManager] View controls initialized');
    }

    zoomIn(amount = 0.25) {
        this.viewZoom = Math.min(4, this.viewZoom + amount);
        this._applyViewTransform();
    }

    zoomOut(amount = 0.25) {
        this.viewZoom = Math.max(0.5, this.viewZoom - amount);
        this._applyViewTransform();
    }

    resetView() {
        this.viewZoom = 1;
        this.viewOffsetX = 0;
        this.viewOffsetY = 0;
        this._applyViewTransform();
    }

    _applyViewTransform() {
        if (!this.app?.stage) return;
        this.app.stage.scale.set(this.viewZoom);
        this.app.stage.x = this.viewOffsetX;
        this.app.stage.y = this.viewOffsetY;
    }

    /**
     * Apply control mode to model's internal systems
     * - strict: Disable ALL internal systems, parameters stay exactly where set
     * - hold: Disable idle motions, keep physics/breath/blink for natural movement
     * - auto: Full internal animations + temporary overrides
     */
    _applyControlMode() {
        if (!this.model) return;

        const internalModel = this.model.internalModel;

        if (this.controlMode === 'strict') {
            // Disable ALL internal systems
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
            console.log('[AvatarManager] Strict mode: All internal systems disabled');

        } else if (this.controlMode === 'hold') {
            // Disable motionManager (idle loops fight with our control)
            if (internalModel.motionManager) {
                internalModel.motionManager.stopAllMotions();
                internalModel.motionManager.update = () => false;
            }
            // Disable expressionManager
            if (internalModel.expressionManager) {
                internalModel.expressionManager.update = () => false;
            }
            // KEEP physics (hair/clothing movement), breath, eyeBlink
            if (this._originalPhysics) internalModel.physics = this._originalPhysics;
            if (this._originalBreath) internalModel.breath = this._originalBreath;
            if (this._originalEyeBlink) internalModel.eyeBlink = this._originalEyeBlink;
            // Only restore pose if not disabled by gesture
            if (this._originalPose && !this._poseDisabledByGesture) {
                internalModel.pose = this._originalPose;
            }
            console.log('[AvatarManager] Hold mode: Idle disabled, physics/breath/blink active');

        } else {
            // Auto mode - restore everything
            if (internalModel.motionManager && this._originalMotionManagerUpdate) {
                internalModel.motionManager.update = this._originalMotionManagerUpdate;
            }
            if (this._originalPhysics) internalModel.physics = this._originalPhysics;
            if (this._originalPose && !this._poseDisabledByGesture) {
                internalModel.pose = this._originalPose;
            }
            if (this._originalEyeBlink) internalModel.eyeBlink = this._originalEyeBlink;
            if (this._originalBreath) internalModel.breath = this._originalBreath;
            console.log('[AvatarManager] Auto mode: All internal systems active');
        }
    }

    /**
     * Set control mode
     */
    setControlMode(mode) {
        this.controlMode = mode;
        this._applyControlMode();
    }

    // === Public API ===

    /**
     * Set avatar state (idle, listening, thinking, speaking)
     */
    setState(state) {
        if (this.stateMachine) {
            this.stateMachine.setState(state);
        }
    }

    /**
     * Set emotion by name
     */
    setEmotion(emotionName, duration = 400) {
        if (this.stateMachine) {
            this.stateMachine.setEmotion(emotionName, duration);
        }
    }

    /**
     * Detect and set emotion from text
     * Returns the detected emotion name
     */
    detectEmotion(text) {
        if (this.emotionDetector) {
            return this.emotionDetector.detect(text);
        }
        return 'neutral';
    }

    /**
     * Prepare emotion from text (detect but with faster transition)
     */
    prepareEmotion(text) {
        const emotion = this.detectEmotion(text);
        this.setEmotion(emotion, 300);
        return emotion;
    }

    /**
     * Connect audio element for lip sync
     */
    connectAudio(audioElement) {
        if (!this.audioAnalyzer) return false;

        // Resume audio context if needed
        this.audioAnalyzer.resume();

        // Connect audio
        const connected = this.audioAnalyzer.connectAudioElement(audioElement);

        if (connected) {
            this.currentAudio = audioElement;
            this._startLipSync();

            // Stop lip sync when audio ends
            audioElement.addEventListener('ended', () => {
                this._stopLipSync();
            }, { once: true });

            audioElement.addEventListener('pause', () => {
                this._stopLipSync();
            }, { once: true });
        }

        return connected;
    }

    /**
     * Start lip sync animation loop
     */
    _startLipSync() {
        if (this.isLipSyncActive) return;
        this.isLipSyncActive = true;

        const animate = () => {
            if (!this.isLipSyncActive) return;

            if (this.audioAnalyzer && this.controller) {
                const mouthValue = this.audioAnalyzer.getMouthValue();
                // Scale down lip sync (0.8 = 80% of original)
                this.controller.setMouthOpen(mouthValue * 0.8);
            }

            requestAnimationFrame(animate);
        };

        animate();
    }

    /**
     * Stop lip sync animation
     */
    _stopLipSync() {
        this.isLipSyncActive = false;
        if (this.controller) {
            this.controller.setMouthOpen(0);
        }
    }

    /**
     * Trigger a blink
     */
    blink() {
        if (this.stateMachine) {
            this.stateMachine.triggerBlink();
        } else if (this.controller) {
            this.controller.blink();
        }
    }

    /**
     * Set lip sync sensitivity
     */
    setSensitivity(value) {
        if (this.audioAnalyzer) {
            this.audioAnalyzer.setSensitivity(value);
        }
    }

    /**
     * Get current state info
     */
    getStateInfo() {
        return {
            isInitialized: this.isInitialized,
            isLipSyncActive: this.isLipSyncActive,
            ...(this.stateMachine?.getStateInfo() || {})
        };
    }

    /**
     * Check if avatar is ready
     */
    isReady() {
        return this.isInitialized && this.model !== null;
    }

    /**
     * Reset to idle neutral state
     */
    reset() {
        this._stopLipSync();
        if (this.stateMachine) {
            this.stateMachine.reset();
        }
        this.setState('idle');
    }

    /**
     * Set a parameter value on the avatar
     */
    setParameter(paramKey, value) {
        if (this.controller) {
            const result = this.controller.setParameter(paramKey, value);
            // Debug: log first few param changes
            if (!this._paramLogCount) this._paramLogCount = 0;
            if (this._paramLogCount < 20) {
                console.log(`[AvatarManager] setParameter: ${paramKey} = ${value} (success: ${result})`);
                this._paramLogCount++;
            }
            return result;
        }
        console.warn('[AvatarManager] setParameter: No controller!');
        return false;
    }

    /**
     * Set part opacity (for showing/hiding model parts like arms)
     */
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
            console.error('[AvatarManager] Error setting part opacity:', e);
        }
        return false;
    }

    /**
     * Cleanup and destroy
     */
    destroy() {
        this._stopLipSync();

        if (this.stateMachine) {
            this.stateMachine.stop();
        }

        if (this.audioAnalyzer) {
            this.audioAnalyzer.destroy();
        }

        if (this.model) {
            this.app.stage.removeChild(this.model);
            this.model.destroy();
        }

        if (this.app) {
            this.app.destroy(true);
        }

        this.isInitialized = false;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AvatarManager };
}
