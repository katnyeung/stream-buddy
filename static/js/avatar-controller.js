/**
 * AvatarController - Controls Live2D model parameters
 * Provides a clean API for manipulating expressions, mouth, eyes, etc.
 * Compatible with both Cubism 2/3 and Cubism 4 models
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
    breath: ['ParamBreath', 'PARAM_BREATH'],

    // Arms - A is rotation (-1 to 1), B is lift (0 to 5)
    armLA: ['ParamArmLA', 'PARAM_ARM_L_A'],
    armRA: ['ParamArmRA', 'PARAM_ARM_R_A'],
    armLB: ['ParamArmLB', 'PARAM_ARM_L_B'],
    armRB: ['ParamArmRB', 'PARAM_ARM_R_B'],

    // Hands - Change is pose (0-1), Angle is rotation (-1 to 1)
    handChangeL: ['ParamHandDhangeL', 'ParamHandChangeL'],  // Note: some models have typo
    handChangeR: ['ParamHandChangeR', 'ParamHandDhangeR'],
    handAngleL: ['ParamHandAngleL'],
    handAngleR: ['ParamHandAngleR'],

    // Extra expressions
    eyeSmileL: ['ParamEyeLSmile'],
    eyeSmileR: ['ParamEyeRSmile'],
    tear: ['ParamTear'],
    tere: ['ParamTere']  // Blush
};

class AvatarController {
    constructor(model) {
        this.model = model;
        this.coreModel = model.internalModel.coreModel;
        this.currentValues = {}; // Track current parameter values
        this.targetValues = {}; // Target values for interpolation
        this.transitionSpeed = 0.15; // Default transition speed (0-1)

        console.log('[AvatarController] Initialized');
    }

    /**
     * Set a parameter value immediately (matches vtuber applyParam)
     */
    setParameter(paramKey, value) {
        if (!this.model) return false;

        const coreModel = this.coreModel;
        const aliases = PARAM_ALIASES[paramKey] || [paramKey];

        for (const name of aliases) {
            try {
                // Try Cubism 4 API (uses getParameterIndex)
                if (typeof coreModel.getParameterIndex === 'function') {
                    const idx = coreModel.getParameterIndex(name);
                    if (idx >= 0) {
                        coreModel.setParameterValueByIndex(idx, value);
                        this.currentValues[paramKey] = value;
                        return true;
                    }
                }
                // Try Cubism 2 API (uses _parameterIds array)
                else if (coreModel._parameterIds || coreModel.parameterIds) {
                    const ids = coreModel._parameterIds || coreModel.parameterIds;
                    const idx = ids.indexOf(name);
                    if (idx >= 0) {
                        if (coreModel.setParamFloat) {
                            coreModel.setParamFloat(name, value);
                            this.currentValues[paramKey] = value;
                            return true;
                        } else if (coreModel._parameterValues) {
                            coreModel._parameterValues[idx] = value;
                            this.currentValues[paramKey] = value;
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

    /**
     * Get current parameter value
     */
    getParameter(paramKey) {
        if (!this.model) return null;

        const coreModel = this.coreModel;
        const aliases = PARAM_ALIASES[paramKey] || [paramKey];

        for (const name of aliases) {
            try {
                // Try Cubism 4 API
                if (typeof coreModel.getParameterIndex === 'function') {
                    const idx = coreModel.getParameterIndex(name);
                    if (idx >= 0) {
                        return coreModel.getParameterValueByIndex(idx);
                    }
                }
                // Try Cubism 2 API
                else if (coreModel._parameterIds || coreModel.parameterIds) {
                    const ids = coreModel._parameterIds || coreModel.parameterIds;
                    const idx = ids.indexOf(name);
                    if (idx >= 0 && coreModel._parameterValues) {
                        return coreModel._parameterValues[idx];
                    }
                }
            } catch (e) {
                // Continue to next alias
            }
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
     * Get all available parameter IDs (for debugging)
     */
    getParameterIds() {
        const coreModel = this.coreModel;

        try {
            // Cubism 2
            if (coreModel._parameterIds) {
                return [...coreModel._parameterIds];
            }
            // Cubism 4
            if (typeof coreModel.getParameterCount === 'function') {
                const ids = [];
                const count = coreModel.getParameterCount();
                for (let i = 0; i < count; i++) {
                    ids.push(coreModel.getParameterId(i));
                }
                return ids;
            }
        } catch (e) {
            console.error('[AvatarController] Error getting parameter IDs:', e);
        }
        return [];
    }

    /**
     * Get parameter info (id, value, min, max) - for debugging
     */
    getParameterInfo() {
        const info = [];
        const coreModel = this.coreModel;

        try {
            // Cubism 2
            if (coreModel._parameterIds) {
                const ids = coreModel._parameterIds;
                const values = coreModel._parameterValues;
                const mins = coreModel._parameterMinimumValues;
                const maxs = coreModel._parameterMaximumValues;

                for (let i = 0; i < ids.length; i++) {
                    info.push({
                        id: ids[i],
                        value: values ? values[i] : 0,
                        min: mins ? mins[i] : 0,
                        max: maxs ? maxs[i] : 1
                    });
                }
            }
            // Cubism 4
            else if (typeof coreModel.getParameterCount === 'function') {
                const count = coreModel.getParameterCount();
                for (let i = 0; i < count; i++) {
                    info.push({
                        id: coreModel.getParameterId(i),
                        value: coreModel.getParameterValueByIndex(i),
                        min: coreModel.getParameterMinimumValue(i),
                        max: coreModel.getParameterMaximumValue(i)
                    });
                }
            }
        } catch (e) {
            console.error('[AvatarController] Error getting parameter info:', e);
        }

        return info;
    }

    /**
     * Reset all parameters to their default values
     */
    resetToDefaults() {
        const coreModel = this.coreModel;

        try {
            // Cubism 2
            if (coreModel._parameterIds && coreModel._parameterDefaultValues) {
                for (let i = 0; i < coreModel._parameterIds.length; i++) {
                    coreModel._parameterValues[i] = coreModel._parameterDefaultValues[i];
                }
            }
            // Cubism 4
            else if (typeof coreModel.getParameterCount === 'function') {
                const count = coreModel.getParameterCount();
                for (let i = 0; i < count; i++) {
                    const defaultValue = coreModel.getParameterDefaultValue(i);
                    coreModel.setParameterValueByIndex(i, defaultValue);
                }
            }
        } catch (e) {
            console.error('[AvatarController] Error resetting to defaults:', e);
        }

        this.currentValues = {};
        this.targetValues = {};
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AvatarController, PARAM_ALIASES };
}
