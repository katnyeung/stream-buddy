/**
 * ActionExecutor - Executes moods and gestures with timing and interpolation
 *
 * Layers:
 *   - Mood Layer: Persistent base expression, smooth transitions
 *   - Gesture Layer: One-shot animations that ADD to mood values
 *   - Lip Sync: Handled separately (mouth controlled by audio)
 *
 * Usage:
 *   const executor = new ActionExecutor(library, setParamCallback);
 *   executor.start();
 *   executor.setMood('happy');
 *   executor.playGesture('nod');
 */

class ActionExecutor {
    /**
     * @param {ActionLibrary} library - Action definitions
     * @param {function(string, number)} setParam - Callback to set avatar parameter
     * @param {function(string, number)} setPartOpacity - Callback to set part opacity (optional)
     */
    constructor(library, setParam, setPartOpacity = null) {
        this.library = library;
        this.setParam = setParam;
        this.setPartOpacity = setPartOpacity;

        // Current mood state
        this.currentMood = null;
        this.currentMoodName = 'neutral';
        this.moodParams = {};  // Current mood parameter values

        // Mood transition
        this.moodTransition = {
            active: false,
            startParams: {},
            targetParams: {},
            startTime: 0,
            duration: 400,
            progress: 1
        };

        // Active gestures (can have multiple)
        this.activeGestures = [];

        // Animation loop
        this.isRunning = false;
        this.lastTime = 0;

        // Parameter exclusions (e.g., mouth during lip sync)
        this.excludedParams = new Set();

        // Arm part visibility state
        this.armPartState = null;  // 'A' = waist arms, 'B' = raised arms, null = no override

        // Arm part fade transition
        this.armFade = {
            active: false,
            fromLayer: null,  // 'A' or 'B'
            toLayer: null,    // 'A' or 'B' or null (model control)
            startTime: 0,
            duration: 500,    // Fade duration in ms
            progress: 0
        };

        // Global intensity multiplier (1.0 = normal, higher = stronger movements)
        this.globalIntensity = 1.0;

        // Initialize with neutral mood
        this._initNeutralMood();
    }

    /**
     * Initialize with neutral mood params
     */
    _initNeutralMood() {
        const neutral = this.library.getMood('neutral');
        if (neutral) {
            this.currentMood = neutral;
            this.currentMoodName = 'neutral';
            this.moodParams = { ...neutral.params };
        }
    }

    /**
     * Start the animation loop
     */
    start() {
        if (this.isRunning) return;
        this.isRunning = true;
        this.lastTime = performance.now();
        this._animationLoop();
        console.log('[ActionExecutor] Started');
    }

    /**
     * Stop the animation loop
     */
    stop() {
        this.isRunning = false;
        console.log('[ActionExecutor] Stopped');
    }

    /**
     * Main animation loop
     */
    _animationLoop() {
        if (!this.isRunning) return;

        const now = performance.now();
        const deltaTime = now - this.lastTime;
        this.lastTime = now;

        this.update(deltaTime);

        requestAnimationFrame(() => this._animationLoop());
    }

    /**
     * Update all animations (called each frame)
     */
    update(deltaTime) {
        // Update mood transition
        this._updateMoodTransition();

        // Update active gestures
        this._updateGestures();

        // Enforce arm part visibility while arm gestures are active
        this._enforceArmPartVisibility();

        // Calculate final parameter values and apply
        this._applyParameters();
    }

    /**
     * Check if any active gesture uses arm B or A params and enforce visibility
     */
    _enforceArmPartVisibility() {
        if (!this.setPartOpacity) return;

        // Check if any active gesture uses arm params
        let needsArmB = false;
        let needsArmA = false;

        for (const gesture of this.activeGestures) {
            if (gesture.usesArmB) needsArmB = true;
            if (gesture.usesArmA) needsArmA = true;
        }

        // Determine target state from active gestures
        const activeLayer = needsArmB ? 'B' : (needsArmA ? 'A' : null);

        // If a new gesture specifies a layer, switch to it
        if (activeLayer !== null && activeLayer !== this.armPartState) {
            // Switching arm layers - could add fade here if needed
            this.armPartState = activeLayer;
            console.log(`[ActionExecutor] Switched to arm layer: ${activeLayer}`);
        }
        // When gesture ends, keep the same arm layer visible (don't switch back)

        // Handle active fade transition (for future use)
        if (this.armFade.active) {
            this._updateArmFade();
            return;
        }

        // Enforce visibility based on current arm state (persists after gesture ends)
        if (this.armPartState === 'B') {
            this.setPartOpacity('Part01ArmRB001', 1);
            this.setPartOpacity('Part01ArmLB001', 1);
            this.setPartOpacity('Part01ArmRA001', 0);
            this.setPartOpacity('Part01ArmLA001', 0);
        } else if (this.armPartState === 'A') {
            this.setPartOpacity('Part01ArmRA001', 1);
            this.setPartOpacity('Part01ArmLA001', 1);
            this.setPartOpacity('Part01ArmRB001', 0);
            this.setPartOpacity('Part01ArmLB001', 0);
        }
        // When armPartState is null, let model control parts naturally
    }

    /**
     * Start fading between arm layers
     */
    _startArmFade(fromLayer, toLayer) {
        this.armFade.active = true;
        this.armFade.fromLayer = fromLayer;
        this.armFade.toLayer = toLayer;
        this.armFade.startTime = performance.now();
        this.armFade.progress = 0;
        console.log(`[ActionExecutor] Starting arm fade: ${fromLayer} -> ${toLayer || 'model control'}`);
    }

    /**
     * Update arm fade transition
     */
    _updateArmFade() {
        if (!this.armFade.active || !this.setPartOpacity) return;

        const elapsed = performance.now() - this.armFade.startTime;
        const progress = Math.min(1, elapsed / this.armFade.duration);

        // Ease out for smooth deceleration
        const eased = 1 - Math.pow(1 - progress, 2);
        this.armFade.progress = eased;

        const fromLayer = this.armFade.fromLayer;
        const toLayer = this.armFade.toLayer;

        if (fromLayer === 'B' && toLayer === null) {
            // Fade out B arms, fade in A arms (back to model's default waist pose)
            const bOpacity = 1 - eased;
            const aOpacity = eased;
            this.setPartOpacity('Part01ArmRB001', bOpacity);
            this.setPartOpacity('Part01ArmLB001', bOpacity);
            this.setPartOpacity('Part01ArmRA001', aOpacity);
            this.setPartOpacity('Part01ArmLA001', aOpacity);
        } else if (fromLayer === 'A' && toLayer === null) {
            // Fade out A arms, fade in B arms
            const aOpacity = 1 - eased;
            const bOpacity = eased;
            this.setPartOpacity('Part01ArmRA001', aOpacity);
            this.setPartOpacity('Part01ArmLA001', aOpacity);
            this.setPartOpacity('Part01ArmRB001', bOpacity);
            this.setPartOpacity('Part01ArmLB001', bOpacity);
        }

        if (progress >= 1) {
            this.armFade.active = false;
            console.log('[ActionExecutor] Arm fade complete');
        }
    }

    /**
     * Set a new mood with smooth transition
     * @param {string} moodName
     * @param {object} options - { intensity, duration }
     */
    setMood(moodName, options = {}) {
        const mood = this.library.getMood(moodName);
        if (!mood) {
            console.warn(`[ActionExecutor] Unknown mood: ${moodName}`);
            return false;
        }

        const intensity = (options.intensity ?? 1) * this.globalIntensity;
        const duration = options.duration ?? mood.transition;

        // Calculate target params with intensity
        const targetParams = {};
        const neutral = this.library.getMood('neutral')?.params || {};

        for (const [key, value] of Object.entries(mood.params)) {
            // Blend between neutral and mood based on intensity
            const neutralValue = neutral[key] || 0;
            targetParams[key] = neutralValue + (value - neutralValue) * intensity;
        }

        // Start transition
        this.moodTransition = {
            active: true,
            startParams: { ...this.moodParams },
            targetParams,
            startTime: performance.now(),
            duration,
            progress: 0
        };

        this.currentMood = mood;
        this.currentMoodName = moodName;

        console.log(`[ActionExecutor] Mood: ${moodName} (intensity: ${intensity}, duration: ${duration}ms)`);
        return true;
    }

    /**
     * Play a one-shot gesture animation
     * @param {string} gestureName
     * @param {object} options - { intensity, duration }
     */
    playGesture(gestureName, options = {}) {
        const gesture = this.library.getGesture(gestureName);
        if (!gesture) {
            console.warn(`[ActionExecutor] Unknown gesture: ${gestureName}`);
            return false;
        }

        const intensity = (options.intensity ?? 1) * this.globalIntensity;
        const duration = options.duration ?? gesture.duration;

        // Check if gesture uses arm parameters
        const usesArmB = this._gestureUsesArmB(gesture);
        const usesArmA = this._gestureUsesArmA(gesture);

        // Show appropriate arm parts
        if (usesArmB && this.setPartOpacity) {
            this._showArmParts('B');
        } else if (usesArmA && this.setPartOpacity) {
            this._showArmParts('A');
        }

        // Create active gesture instance
        const activeGesture = {
            name: gestureName,
            keyframes: gesture.keyframes,
            duration,
            intensity,
            relative: gesture.relative !== false,  // Default true
            startTime: performance.now(),
            currentValues: {},  // Current interpolated values
            usesArmB,
            usesArmA
        };

        // Add to active gestures
        this.activeGestures.push(activeGesture);

        console.log(`[ActionExecutor] Gesture: ${gestureName} (intensity: ${intensity}, duration: ${duration}ms)`);
        return true;
    }

    /**
     * Check if gesture uses arm B parameters (raised/crossed arm)
     */
    _gestureUsesArmB(gesture) {
        if (!gesture.keyframes) return false;
        return gesture.keyframes.some(kf =>
            kf.armLB !== undefined || kf.armRB !== undefined
        );
    }

    /**
     * Check if gesture uses arm A parameters (waist/rotation arm)
     */
    _gestureUsesArmA(gesture) {
        if (!gesture.keyframes) return false;
        return gesture.keyframes.some(kf =>
            kf.armLA !== undefined || kf.armRA !== undefined
        );
    }

    /**
     * Show arm parts for a specific layer
     * @param {'A'|'B'} layer - Which arm layer to show
     */
    _showArmParts(layer) {
        if (!this.setPartOpacity) return;

        if (layer === 'B') {
            // Show raised/crossed arms (B), hide waist arms (A)
            this.setPartOpacity('Part01ArmRB001', 1);
            this.setPartOpacity('Part01ArmLB001', 1);
            this.setPartOpacity('Part01ArmRA001', 0);
            this.setPartOpacity('Part01ArmLA001', 0);
            this.armPartState = 'B';
            console.log('[ActionExecutor] Showing arm B parts (raised/crossed)');
        } else if (layer === 'A') {
            // Show waist arms (A), hide raised/crossed arms (B)
            this.setPartOpacity('Part01ArmRA001', 1);
            this.setPartOpacity('Part01ArmLA001', 1);
            this.setPartOpacity('Part01ArmRB001', 0);
            this.setPartOpacity('Part01ArmLB001', 0);
            this.armPartState = 'A';
            console.log('[ActionExecutor] Showing arm A parts (waist)');
        }
    }

    /**
     * Reset arm parts to default (let model control)
     */
    _resetArmParts() {
        // Don't force reset - let the model's auto mode handle it
        this.armPartState = null;
        console.log('[ActionExecutor] Arm parts reset to model control');
    }

    /**
     * Execute a compound action (mood + gesture)
     * @param {string} actionName
     * @param {object} options
     */
    executeAction(actionName, options = {}) {
        const action = this.library.getAction(actionName);
        if (!action) {
            console.warn(`[ActionExecutor] Unknown action: ${actionName}`);
            return false;
        }

        // Apply mood if defined
        if (action.moodName) {
            this.setMood(action.moodName, options);
        }

        // Play gesture if defined
        if (action.gestureName) {
            this.playGesture(action.gestureName, options);
        }

        console.log(`[ActionExecutor] Action: ${actionName}`);
        return true;
    }

    /**
     * Execute parsed action from ActionParser
     * @param {{ type: string, name: string, params: object }} action
     */
    executeFromParsed(action) {
        const options = {
            intensity: action.params.intensity,
            duration: action.params.duration ? action.params.duration * 1000 : undefined
        };

        switch (action.type) {
            case 'mood':
                return this.setMood(action.name, options);
            case 'gesture':
                return this.playGesture(action.name, options);
            case 'action':
                return this.executeAction(action.name, options);
            // Alias categories - resolve through library and play as gesture
            case 'eye':
            case 'head':
            case 'body':
            case 'brow': {
                const resolved = this.library.get(action.type, action.name);
                if (resolved && resolved.type === 'gesture' && resolved.data) {
                    console.log(`[ActionExecutor] ${action.type}:${action.name} -> gesture:${resolved.name}`);
                    return this.playGesture(resolved.name, options);
                }
                console.warn(`[ActionExecutor] Unknown ${action.type}: ${action.name}`);
                return false;
            }
            default:
                console.warn(`[ActionExecutor] Unknown action type: ${action.type}`);
                return false;
        }
    }

    /**
     * Execute multiple parsed actions
     * @param {Array} actions - Array from ActionParser
     */
    executeActions(actions) {
        for (const action of actions) {
            this.executeFromParsed(action);
        }
    }

    /**
     * Clear current mood - stops enforcing mood parameters
     * Allows manual control of parameters again
     */
    clearMood() {
        this.currentMood = null;
        this.currentMoodName = null;
        this.moodParams = {};
        this.moodTransition.active = false;
        console.log('[ActionExecutor] Mood cleared - manual control enabled');
    }

    /**
     * Clear all active gestures
     */
    clearGestures() {
        this.activeGestures = [];
        console.log('[ActionExecutor] Gestures cleared');
    }

    /**
     * Clear everything - mood, gestures, arm state
     * Full reset to allow manual control
     */
    clearAll() {
        this.clearMood();
        this.clearGestures();
        this.armPartState = null;
        console.log('[ActionExecutor] All actions cleared - full manual control');
    }

    /**
     * Exclude a parameter from being controlled (e.g., for lip sync)
     * @param {string} paramName
     */
    excludeParam(paramName) {
        this.excludedParams.add(paramName);
    }

    /**
     * Re-include a parameter
     * @param {string} paramName
     */
    includeParam(paramName) {
        this.excludedParams.delete(paramName);
    }

    /**
     * Update mood transition
     */
    _updateMoodTransition() {
        if (!this.moodTransition.active) return;

        const elapsed = performance.now() - this.moodTransition.startTime;
        let progress = Math.min(1, elapsed / this.moodTransition.duration);

        // Ease out cubic for smooth deceleration
        const eased = 1 - Math.pow(1 - progress, 3);

        // Interpolate parameters
        for (const [key, targetValue] of Object.entries(this.moodTransition.targetParams)) {
            const startValue = this.moodTransition.startParams[key] ?? 0;
            this.moodParams[key] = startValue + (targetValue - startValue) * eased;
        }

        this.moodTransition.progress = progress;

        if (progress >= 1) {
            this.moodTransition.active = false;
            this.moodParams = { ...this.moodTransition.targetParams };
        }
    }

    /**
     * Update all active gestures
     */
    _updateGestures() {
        const now = performance.now();
        const completedIndices = [];

        for (let i = 0; i < this.activeGestures.length; i++) {
            const gesture = this.activeGestures[i];
            const elapsed = now - gesture.startTime;
            const progress = Math.min(1, elapsed / gesture.duration);

            if (progress >= 1) {
                // Gesture complete
                completedIndices.push(i);
                gesture.currentValues = {};  // Reset to zero offset
            } else {
                // Interpolate keyframes
                gesture.currentValues = this._interpolateKeyframes(
                    gesture.keyframes,
                    progress,
                    gesture.intensity
                );
            }
        }

        // Remove completed gestures (reverse order to preserve indices)
        for (let i = completedIndices.length - 1; i >= 0; i--) {
            const idx = completedIndices[i];
            console.log(`[ActionExecutor] Gesture complete: ${this.activeGestures[idx].name}`);
            this.activeGestures.splice(idx, 1);
        }
    }

    /**
     * Interpolate keyframe values at given progress
     * @param {Array} keyframes - [{t: 0, param1: val1}, {t: 0.5, param1: val2}, ...]
     * @param {number} progress - 0-1
     * @param {number} intensity - 0-1
     * @returns {object} Interpolated parameter values
     */
    _interpolateKeyframes(keyframes, progress, intensity = 1) {
        const result = {};

        // Find surrounding keyframes
        let prevFrame = keyframes[0];
        let nextFrame = keyframes[keyframes.length - 1];

        for (let i = 0; i < keyframes.length - 1; i++) {
            if (keyframes[i].t <= progress && keyframes[i + 1].t >= progress) {
                prevFrame = keyframes[i];
                nextFrame = keyframes[i + 1];
                break;
            }
        }

        // Calculate local progress between frames
        const frameRange = nextFrame.t - prevFrame.t;
        const localProgress = frameRange > 0 ? (progress - prevFrame.t) / frameRange : 0;

        // Ease in-out for smooth motion
        const eased = localProgress < 0.5
            ? 2 * localProgress * localProgress
            : 1 - Math.pow(-2 * localProgress + 2, 2) / 2;

        // Interpolate all parameters in keyframes
        const allParams = new Set();
        for (const frame of keyframes) {
            for (const key of Object.keys(frame)) {
                if (key !== 't') allParams.add(key);
            }
        }

        for (const param of allParams) {
            const prevVal = prevFrame[param] ?? 0;
            const nextVal = nextFrame[param] ?? 0;
            result[param] = (prevVal + (nextVal - prevVal) * eased) * intensity;
        }

        return result;
    }

    /**
     * Apply final parameter values to avatar
     */
    _applyParameters() {
        // Start with mood params
        const finalParams = { ...this.moodParams };

        // Add gesture offsets
        for (const gesture of this.activeGestures) {
            for (const [key, value] of Object.entries(gesture.currentValues)) {
                if (gesture.relative) {
                    // Relative: add to mood value
                    finalParams[key] = (finalParams[key] || 0) + value;
                } else {
                    // Absolute: override mood value
                    finalParams[key] = value;
                }
            }
        }

        // Debug: log once when params exist
        if (!this._applyLoggedOnce && Object.keys(finalParams).length > 0) {
            console.log('[ActionExecutor] _applyParameters finalParams:', Object.keys(finalParams));
            this._applyLoggedOnce = true;
        }

        // Apply parameters (excluding lip sync params)
        for (const [key, value] of Object.entries(finalParams)) {
            if (!this.excludedParams.has(key)) {
                this.setParam(key, value);
            }
        }
    }

    /**
     * Get current state info
     */
    getState() {
        return {
            mood: this.currentMoodName,
            isMoodTransitioning: this.moodTransition.active,
            activeGestures: this.activeGestures.map(g => g.name),
            excludedParams: Array.from(this.excludedParams)
        };
    }

    /**
     * Reset to neutral
     */
    reset() {
        this.setMood('neutral', { duration: 200 });
        this.activeGestures = [];
        this.excludedParams.clear();
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ActionExecutor };
}
