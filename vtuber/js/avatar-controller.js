/**
 * AvatarController - Controls Live2D model parameters
 * Provides a clean API for manipulating expressions, mouth, eyes, etc.
 */

// Parameter name mappings for different model conventions
const PARAM_ALIASES = {
    // Head movement
    angleX: ['ParamAngleX', 'PARAM_ANGLE_X', 'Angle X'],
    angleY: ['ParamAngleY', 'PARAM_ANGLE_Y', 'Angle Y'],
    angleZ: ['ParamAngleZ', 'PARAM_ANGLE_Z', 'Angle Z'],

    // Body
    bodyAngleX: ['ParamBodyAngleX', 'PARAM_BODY_ANGLE_X'],
    bodyAngleY: ['ParamBodyAngleY', 'PARAM_BODY_ANGLE_Y'],
    bodyAngleZ: ['ParamBodyAngleZ', 'PARAM_BODY_ANGLE_Z'],

    // Mouth
    mouthOpen: ['ParamMouthOpenY', 'PARAM_MOUTH_OPEN_Y', 'ParamMouthOpen'],
    mouthForm: ['ParamMouthForm', 'PARAM_MOUTH_FORM'],

    // Eyes
    eyeOpenL: ['ParamEyeLOpen', 'PARAM_EYE_L_OPEN'],
    eyeOpenR: ['ParamEyeROpen', 'PARAM_EYE_R_OPEN'],
    eyeBallX: ['ParamEyeBallX', 'PARAM_EYE_BALL_X'],
    eyeBallY: ['ParamEyeBallY', 'PARAM_EYE_BALL_Y'],

    // Eyebrows
    browLY: ['ParamBrowLY', 'PARAM_BROW_L_Y'],
    browRY: ['ParamBrowRY', 'PARAM_BROW_R_Y'],

    // Breathing
    breath: ['ParamBreath', 'PARAM_BREATH']
};

class AvatarController {
    constructor(model) {
        this.model = model;
        this.coreModel = model.internalModel.coreModel;
        this.parameterCache = new Map(); // Cache parameter indices for performance
        this.currentValues = {}; // Track current parameter values
        this.targetValues = {}; // Target values for interpolation
        this.transitionSpeed = 0.15; // Default transition speed (0-1)

        // Build parameter index cache
        this._buildParameterCache();
    }

    /**
     * Build a cache of parameter indices for faster access
     */
    _buildParameterCache() {
        const count = this.coreModel.getParameterCount();

        for (let i = 0; i < count; i++) {
            const id = this.coreModel.getParameterId(i);
            this.parameterCache.set(id, i);
        }
    }

    /**
     * Get parameter index by name (checks aliases)
     */
    _getParameterIndex(paramKey) {
        // Check direct cache first
        if (this.parameterCache.has(paramKey)) {
            return this.parameterCache.get(paramKey);
        }

        // Check aliases
        const aliases = PARAM_ALIASES[paramKey] || [];
        for (const alias of aliases) {
            if (this.parameterCache.has(alias)) {
                return this.parameterCache.get(alias);
            }
        }

        return -1;
    }

    /**
     * Set a parameter value immediately
     */
    setParameter(paramKey, value) {
        const index = this._getParameterIndex(paramKey);
        if (index >= 0) {
            this.coreModel.setParameterValueByIndex(index, value);
            this.currentValues[paramKey] = value;
            return true;
        }
        return false;
    }

    /**
     * Get current parameter value
     */
    getParameter(paramKey) {
        const index = this._getParameterIndex(paramKey);
        if (index >= 0) {
            return this.coreModel.getParameterValueByIndex(index);
        }
        return null;
    }

    /**
     * Set target value for smooth interpolation
     */
    setTargetParameter(paramKey, value) {
        this.targetValues[paramKey] = value;
    }

    /**
     * Update interpolation (call in animation loop)
     */
    updateInterpolation() {
        for (const [paramKey, targetValue] of Object.entries(this.targetValues)) {
            const currentValue = this.currentValues[paramKey] ?? this.getParameter(paramKey) ?? 0;
            const newValue = currentValue + (targetValue - currentValue) * this.transitionSpeed;

            // Only update if difference is significant
            if (Math.abs(newValue - currentValue) > 0.001) {
                this.setParameter(paramKey, newValue);
            }
        }
    }

    // === Convenience Methods ===

    /**
     * Set mouth open value (0-1)
     */
    setMouthOpen(value) {
        return this.setParameter('mouthOpen', Math.max(0, Math.min(1, value)));
    }

    /**
     * Set mouth form (-1 = frown, 0 = neutral, 1 = smile)
     */
    setMouthForm(value) {
        return this.setParameter('mouthForm', Math.max(-1, Math.min(1, value)));
    }

    /**
     * Set both eyes open value (0-1)
     */
    setEyesOpen(value) {
        const v = Math.max(0, Math.min(1.3, value));
        this.setParameter('eyeOpenL', v);
        this.setParameter('eyeOpenR', v);
    }

    /**
     * Set individual eye open values
     */
    setEyeOpenLeft(value) {
        return this.setParameter('eyeOpenL', Math.max(0, Math.min(1.3, value)));
    }

    setEyeOpenRight(value) {
        return this.setParameter('eyeOpenR', Math.max(0, Math.min(1.3, value)));
    }

    /**
     * Set eye ball position
     */
    setEyeBallPosition(x, y) {
        this.setParameter('eyeBallX', Math.max(-1, Math.min(1, x)));
        this.setParameter('eyeBallY', Math.max(-1, Math.min(1, y)));
    }

    /**
     * Set head angle
     */
    setHeadAngle(x, y, z) {
        if (x !== undefined) this.setParameter('angleX', x);
        if (y !== undefined) this.setParameter('angleY', y);
        if (z !== undefined) this.setParameter('angleZ', z);
    }

    /**
     * Set body angle
     */
    setBodyAngle(x, y, z) {
        if (x !== undefined) this.setParameter('bodyAngleX', x);
        if (y !== undefined) this.setParameter('bodyAngleY', y);
        if (z !== undefined) this.setParameter('bodyAngleZ', z);
    }

    /**
     * Set eyebrow position (-1 to 1)
     */
    setEyebrows(left, right) {
        if (left !== undefined) this.setParameter('browLY', left);
        if (right !== undefined) this.setParameter('browRY', right ?? left);
    }

    /**
     * Apply a parameter preset object
     */
    applyPreset(preset, immediate = true) {
        for (const [param, value] of Object.entries(preset)) {
            if (immediate) {
                this.setParameter(param, value);
            } else {
                this.setTargetParameter(param, value);
            }
        }
    }

    /**
     * Trigger a blink animation
     */
    blink(duration = 150) {
        const originalL = this.getParameter('eyeOpenL') ?? 1;
        const originalR = this.getParameter('eyeOpenR') ?? 1;

        // Close eyes
        this.setEyesOpen(0);

        // Reopen after duration
        setTimeout(() => {
            this.setEyeOpenLeft(originalL);
            this.setEyeOpenRight(originalR);
        }, duration);
    }

    /**
     * Get all available parameter IDs
     */
    getParameterIds() {
        return Array.from(this.parameterCache.keys());
    }

    /**
     * Get parameter info (id, value, min, max)
     */
    getParameterInfo() {
        const info = [];
        const count = this.coreModel.getParameterCount();

        for (let i = 0; i < count; i++) {
            info.push({
                id: this.coreModel.getParameterId(i),
                value: this.coreModel.getParameterValueByIndex(i),
                min: this.coreModel.getParameterMinimumValue(i),
                max: this.coreModel.getParameterMaximumValue(i)
            });
        }

        return info;
    }

    /**
     * Reset all parameters to their default values
     */
    resetToDefaults() {
        const count = this.coreModel.getParameterCount();

        for (let i = 0; i < count; i++) {
            const defaultValue = this.coreModel.getParameterDefaultValue(i);
            this.coreModel.setParameterValueByIndex(i, defaultValue);
        }

        this.currentValues = {};
        this.targetValues = {};
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AvatarController, PARAM_ALIASES };
}
