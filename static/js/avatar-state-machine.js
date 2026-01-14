/**
 * AvatarStateMachine - Manages avatar states, transitions, and animations
 * States: idle, listening, thinking, speaking
 * Features: automatic blinking, idle body sway, emotion-based expressions
 */

class AvatarStateMachine {
    constructor(avatarController, emotionDetector) {
        this.controller = avatarController;
        this.emotionDetector = emotionDetector;

        // Current state
        this.currentState = 'idle';
        this.currentEmotion = 'neutral';

        // Instant mode - skip transitions for strict real-time control
        this.instantMode = false;
        this.defaultTransitionDuration = 400; // ms

        // Transition tracking
        this.transitionProgress = 1;
        this.transitionDuration = this.defaultTransitionDuration;
        this.transitionStartTime = 0;
        this.startParams = {};
        this.targetParams = {};

        // Emotion hold/decay system
        this.emotionHoldTime = 5000; // Hold emotion for 5 seconds before decay
        this.emotionSetTime = 0;
        this.autoDecayEnabled = false; // Disabled by default for LLM control

        // Idle animation
        this.idleTime = 0;
        this.idleOffset = {};

        // Blinking
        this.lastBlinkTime = 0;
        this.blinkInterval = 3000 + Math.random() * 2000;
        this.isBlinking = false;
        this.blinkProgress = 0;
        this.blinkDuration = 150; // ms

        // Animation loop tracking
        this.isAnimating = false;
        this.lastUpdateTime = 0;
    }

    /**
     * Start the animation loop
     */
    start() {
        if (this.isAnimating) return;
        this.isAnimating = true;
        this.lastUpdateTime = performance.now();
        this._animationLoop();
    }

    /**
     * Stop the animation loop
     */
    stop() {
        this.isAnimating = false;
    }

    /**
     * Main animation loop
     */
    _animationLoop() {
        if (!this.isAnimating) return;

        const now = performance.now();
        const deltaTime = now - this.lastUpdateTime;
        this.lastUpdateTime = now;

        this.update(deltaTime);

        requestAnimationFrame(() => this._animationLoop());
    }

    /**
     * Update all animations (called each frame)
     */
    update(deltaTime) {
        // Check for emotion auto-decay
        this._checkEmotionDecay();

        // Update emotion transition
        this._updateTransition();

        // Update idle animation
        this._updateIdleAnimation(deltaTime);

        // Update blinking
        this._updateBlinking();

        // Apply all parameters
        this._applyParameters();
    }

    /**
     * Check if emotion should decay back to neutral
     */
    _checkEmotionDecay() {
        if (!this.autoDecayEnabled) return;
        if (this.currentEmotion === 'neutral') return;

        const elapsed = performance.now() - this.emotionSetTime;
        if (elapsed > this.emotionHoldTime) {
            console.log(`[AvatarState] Emotion decay: ${this.currentEmotion} -> neutral`);
            this.setEmotion('neutral');
        }
    }

    /**
     * Set avatar state
     */
    setState(newState) {
        if (this.currentState === newState) return;

        const previousState = this.currentState;
        this.currentState = newState;

        console.log(`[AvatarState] ${previousState} -> ${newState}`);

        // Adjust idle variation based on state
        switch (newState) {
            case 'thinking':
                // More subtle movement while thinking
                this.idleMultiplier = 0.5;
                break;
            case 'speaking':
                // Moderate movement while speaking
                this.idleMultiplier = 0.7;
                break;
            case 'listening':
                // Alert but calm
                this.idleMultiplier = 0.8;
                break;
            default:
                this.idleMultiplier = 1.0;
        }
    }

    /**
     * Enable/disable instant mode (skip transitions for strict control)
     */
    setInstantMode(enabled) {
        this.instantMode = enabled;
        console.log(`[AvatarState] Instant mode: ${enabled ? 'ON' : 'OFF'}`);
    }

    /**
     * Enable/disable auto decay (emotion returns to neutral after hold time)
     */
    setAutoDecay(enabled, holdTimeMs = 5000) {
        this.autoDecayEnabled = enabled;
        this.emotionHoldTime = holdTimeMs;
        console.log(`[AvatarState] Auto decay: ${enabled ? 'ON' : 'OFF'}, hold: ${holdTimeMs}ms`);
    }

    /**
     * Set emotion with smooth transition (or instant if instantMode is on)
     */
    setEmotion(emotionName, duration = null) {
        if (!this.emotionDetector) return;

        const emotion = this.emotionDetector.getEmotion(emotionName);
        if (!emotion) return;

        this.currentEmotion = emotionName;
        this.targetParams = { ...emotion.params };
        this.emotionSetTime = performance.now(); // Track when emotion was set

        // Store idle variation for this emotion
        this.currentIdleVariation = emotion.idleVariation || {};

        if (this.instantMode) {
            // Instant mode: apply immediately, no transition
            this.transitionProgress = 1;
            this.startParams = { ...this.targetParams };
            // Apply all params immediately
            this._applyParameters();
        } else {
            // Normal mode: smooth transition
            this.startParams = { ...this._getCurrentParams() };
            this.transitionProgress = 0;
            this.transitionStartTime = performance.now();
            this.transitionDuration = duration ?? this.defaultTransitionDuration;
        }
    }

    /**
     * Detect and set emotion from text
     */
    setEmotionFromText(text) {
        if (!this.emotionDetector) return 'neutral';

        const emotion = this.emotionDetector.detect(text);
        this.setEmotion(emotion);
        return emotion;
    }

    /**
     * Update emotion transition
     */
    _updateTransition() {
        if (this.transitionProgress >= 1) return;

        const now = performance.now();
        const elapsed = now - this.transitionStartTime;
        this.transitionProgress = Math.min(1, elapsed / this.transitionDuration);

        // Ease out cubic for smooth deceleration
        const eased = 1 - Math.pow(1 - this.transitionProgress, 3);

        // Interpolate parameters
        for (const [key, targetValue] of Object.entries(this.targetParams)) {
            const startValue = this.startParams[key] || 0;
            const currentParams = this._getCurrentParams();
            currentParams[key] = startValue + (targetValue - startValue) * eased;
        }
    }

    /**
     * Update idle animation (breathing, subtle movement)
     */
    _updateIdleAnimation(deltaTime) {
        this.idleTime += deltaTime;

        const variation = this.currentIdleVariation || { angleX: 3, angleY: 2, angleZ: 2 };
        const multiplier = this.idleMultiplier || 1.0;

        for (const [key, amplitude] of Object.entries(variation)) {
            // Multiple sine waves for organic movement
            const wave1 = Math.sin(this.idleTime * 0.0008) * amplitude * 0.5;
            const wave2 = Math.sin(this.idleTime * 0.0013) * amplitude * 0.3;
            const wave3 = Math.sin(this.idleTime * 0.0019) * amplitude * 0.2;
            this.idleOffset[key] = (wave1 + wave2 + wave3) * multiplier;
        }

        // Breathing effect on body
        const breathCycle = Math.sin(this.idleTime * 0.002) * 2;
        this.idleOffset.bodyAngleY = breathCycle * multiplier;
    }

    /**
     * Update blinking animation
     */
    _updateBlinking() {
        const now = performance.now();

        if (!this.isBlinking) {
            // Check if it's time to blink
            if (now - this.lastBlinkTime > this.blinkInterval) {
                this.isBlinking = true;
                this.blinkProgress = 0;
                this.lastBlinkTime = now;
                // Randomize next blink interval (2-5 seconds)
                this.blinkInterval = 2000 + Math.random() * 3000;
            }
        } else {
            // Progress the blink
            this.blinkProgress += 16 / this.blinkDuration; // Assuming ~60fps
            if (this.blinkProgress >= 1) {
                this.isBlinking = false;
            }
        }
    }

    /**
     * Apply all parameters to the controller
     */
    _applyParameters() {
        if (!this.controller) return;

        // Parameter name mapping
        const paramMapping = {
            angleX: 'angleX',
            angleY: 'angleY',
            angleZ: 'angleZ',
            mouthForm: 'mouthForm',
            eyeOpenL: 'eyeOpenL',
            eyeOpenR: 'eyeOpenR',
            eyeBallX: 'eyeBallX',
            eyeBallY: 'eyeBallY',
            browLY: 'browLY',
            browRY: 'browRY',
            bodyAngleX: 'bodyAngleX',
            bodyAngleY: 'bodyAngleY',
            bodyAngleZ: 'bodyAngleZ'
        };

        for (const [key, paramName] of Object.entries(paramMapping)) {
            let value = this.targetParams[key] || 0;

            // Add idle offset
            if (this.idleOffset[key]) {
                value += this.idleOffset[key];
            }

            // Apply blink to eyes
            if ((key === 'eyeOpenL' || key === 'eyeOpenR') && this.isBlinking) {
                // Sine curve for natural blink (close and open)
                const blinkCurve = Math.sin(this.blinkProgress * Math.PI);
                value *= (1 - blinkCurve * 0.95);
            }

            this.controller.setParameter(paramName, value);
        }
    }

    /**
     * Get current interpolated parameters
     */
    _getCurrentParams() {
        const params = {};
        const progress = this.transitionProgress;
        const eased = 1 - Math.pow(1 - progress, 3);

        for (const [key, targetValue] of Object.entries(this.targetParams)) {
            const startValue = this.startParams[key] || 0;
            params[key] = startValue + (targetValue - startValue) * eased;
        }

        return params;
    }

    /**
     * Force a blink
     */
    triggerBlink() {
        this.isBlinking = true;
        this.blinkProgress = 0;
    }

    /**
     * Get current state info
     */
    getStateInfo() {
        return {
            state: this.currentState,
            emotion: this.currentEmotion,
            isTransitioning: this.transitionProgress < 1,
            isBlinking: this.isBlinking,
            instantMode: this.instantMode,
            autoDecayEnabled: this.autoDecayEnabled,
            emotionHoldTime: this.emotionHoldTime
        };
    }

    /**
     * Reset to neutral idle state
     */
    reset() {
        this.currentState = 'idle';
        this.currentEmotion = 'neutral';
        this.setEmotion('neutral', 200);
        this.idleTime = 0;
        this.idleOffset = {};
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AvatarStateMachine };
}
