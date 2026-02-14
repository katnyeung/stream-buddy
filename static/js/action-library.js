/**
 * ActionLibrary - Predefined moods, gestures, and compound actions
 *
 * Moods: Persistent expressions (stay until changed)
 * Gestures: One-shot animations (play once and return)
 * Actions: Compound mood+gesture combinations
 *
 * Parameter ranges (typical Live2D):
 *   angleX/Y/Z: -30 to 30 (head rotation)
 *   mouthOpen: 0 to 1
 *   mouthForm: -1 to 1 (frown to smile)
 *   eyeOpenL/R: 0 to 1.3
 *   eyeBallX/Y: -1 to 1
 *   browLY/RY: -1 to 1
 *   bodyAngleX/Y/Z: -15 to 15
 *   armLA/armRA: -10 to 10 (arm angle, if model supports)
 *   handL/handR: 0 to 1 (hand open/close, if model supports)
 */

const ACTION_LIBRARY = {
    // ============================================
    // MOODS - Persistent expressions
    // ============================================
    moods: {
        neutral: {
            params: {
                angleX: 0, angleY: 0, angleZ: 2,
                mouthForm: 0,
                eyeOpenL: 1, eyeOpenR: 1,
                eyeBallX: 0, eyeBallY: 0,
                browLY: 0, browRY: 0
            },
            transition: 400
        },

        happy: {
            params: {
                angleX: 5, angleY: -3, angleZ: 3,
                mouthForm: 0.7,
                eyeOpenL: 0.85, eyeOpenR: 0.85,
                eyeBallY: -0.1,
                browLY: 0.2, browRY: 0.2
            },
            transition: 400
        },

        friendly: {
            params: {
                angleX: 3, angleY: -2, angleZ: 5,
                mouthForm: 0.5,
                eyeOpenL: 0.9, eyeOpenR: 0.9,
                browLY: 0.1, browRY: 0.1
            },
            transition: 350
        },

        curious: {
            params: {
                angleX: -5, angleY: 5, angleZ: 10,
                mouthForm: 0.1,
                eyeOpenL: 1.1, eyeOpenR: 1.1,
                eyeBallY: -0.2,
                browLY: 0.4, browRY: 0.3
            },
            transition: 500
        },

        thinking: {
            params: {
                angleX: -5, angleY: 5, angleZ: 3,
                mouthForm: 0.1,
                eyeOpenL: 0.8, eyeOpenR: 0.85,
                eyeBallX: 0, eyeBallY: 0,
                browLY: -0.1, browRY: 0.2
            },
            transition: 600
        },

        surprised: {
            params: {
                angleX: 0, angleY: -6, angleZ: 0,
                mouthOpen: 0.4, mouthForm: 0,
                eyeOpenL: 1.3, eyeOpenR: 1.3,
                browLY: 0.6, browRY: 0.6
            },
            transition: 150
        },

        sad: {
            params: {
                angleX: -8, angleY: 12, angleZ: -3,
                mouthForm: -0.4,
                eyeOpenL: 0.6, eyeOpenR: 0.6,
                eyeBallY: 0.3,
                browLY: -0.4, browRY: -0.4
            },
            transition: 700
        },

        excited: {
            params: {
                angleX: 5, angleY: -8, angleZ: 8,
                mouthForm: 0.9, mouthOpen: 0.2,
                eyeOpenL: 1.2, eyeOpenR: 1.2,
                browLY: 0.5, browRY: 0.5
            },
            transition: 250
        },

        serious: {
            params: {
                angleX: 0, angleY: 0, angleZ: 0,
                mouthForm: -0.2,
                eyeOpenL: 0.9, eyeOpenR: 0.9,
                browLY: -0.2, browRY: -0.2
            },
            transition: 500
        },

        concerned: {
            params: {
                angleX: -5, angleY: 3, angleZ: -5,
                mouthForm: -0.2,
                eyeOpenL: 0.95, eyeOpenR: 0.95,
                eyeBallY: -0.1,
                browLY: -0.3, browRY: 0.1
            },
            transition: 450
        },

        skeptical: {
            params: {
                angleX: -8, angleY: 5, angleZ: 8,
                mouthForm: -0.1,
                eyeOpenL: 0.7, eyeOpenR: 1.0,
                browLY: -0.2, browRY: 0.3
            },
            transition: 400
        },

        confident: {
            params: {
                angleX: 5, angleY: -5, angleZ: 0,
                mouthForm: 0.3,
                eyeOpenL: 0.9, eyeOpenR: 0.9,
                eyeBallY: -0.1,
                browLY: 0.1, browRY: 0.1
            },
            transition: 400
        },

        amused: {
            params: {
                angleX: 3, angleY: -2, angleZ: 6,
                mouthForm: 0.6,
                eyeOpenL: 0.75, eyeOpenR: 0.75,
                browLY: 0.2, browRY: 0.2
            },
            transition: 350
        },

        embarrassed: {
            params: {
                angleX: -10, angleY: 8, angleZ: -8,
                mouthForm: 0.2,
                eyeOpenL: 0.7, eyeOpenR: 0.7,
                eyeBallX: 0.3, eyeBallY: 0.2
            },
            transition: 400
        },

        annoyed: {
            params: {
                angleX: -3, angleY: 0, angleZ: 0,
                mouthForm: -0.3,
                eyeOpenL: 0.8, eyeOpenR: 0.8,
                browLY: -0.4, browRY: -0.4
            },
            transition: 350
        },

        proud: {
            params: {
                angleX: 8, angleY: -8, angleZ: 0,
                mouthForm: 0.4,
                eyeOpenL: 0.85, eyeOpenR: 0.85,
                eyeBallY: -0.2
            },
            transition: 500
        },

        shy: {
            params: {
                angleX: -12, angleY: 10, angleZ: 10,
                mouthForm: 0.2,
                eyeOpenL: 0.6, eyeOpenR: 0.6,
                eyeBallX: 0.4, eyeBallY: 0.2
            },
            transition: 500
        },

        determined: {
            params: {
                angleX: 0, angleY: -5, angleZ: 0,
                mouthForm: 0,
                eyeOpenL: 1.0, eyeOpenR: 1.0,
                browLY: -0.2, browRY: -0.2
            },
            transition: 400
        },

        sleepy: {
            params: {
                angleX: -5, angleY: 5, angleZ: -5,
                mouthForm: 0,
                eyeOpenL: 0.4, eyeOpenR: 0.4,
                eyeBallY: 0.2
            },
            transition: 800
        },

        mischievous: {
            params: {
                angleX: 5, angleY: -3, angleZ: 8,
                mouthForm: 0.5,
                eyeOpenL: 0.9, eyeOpenR: 0.7,
                browLY: 0.3, browRY: -0.1
            },
            transition: 350
        }
    },

    // ============================================
    // GESTURES - One-shot animations with keyframes
    // Values are RELATIVE (added as offset to current mood)
    // ============================================
    gestures: {
        // === HEAD NODS ===
        nod: {
            keyframes: [
                { t: 0.0, angleY: 0 },
                { t: 0.25, angleY: -12 },
                { t: 0.5, angleY: 0 },
                { t: 0.75, angleY: -8 },
                { t: 1.0, angleY: 0 }
            ],
            duration: 1000,  // Slower, more visible
            relative: true
        },

        nod_slow: {
            keyframes: [
                { t: 0.0, angleY: 0 },
                { t: 0.3, angleY: -12 },
                { t: 0.6, angleY: 0 },
                { t: 1.0, angleY: 0 }
            ],
            duration: 1000,
            relative: true
        },

        nod_fast: {
            keyframes: [
                { t: 0.0, angleY: 0 },
                { t: 0.2, angleY: -8 },
                { t: 0.4, angleY: 0 },
                { t: 0.6, angleY: -6 },
                { t: 0.8, angleY: 0 },
                { t: 1.0, angleY: 0 }
            ],
            duration: 400,
            relative: true
        },

        nod_double: {
            keyframes: [
                { t: 0.0, angleY: 0 },
                { t: 0.15, angleY: -10 },
                { t: 0.3, angleY: 0 },
                { t: 0.45, angleY: -10 },
                { t: 0.6, angleY: 0 },
                { t: 1.0, angleY: 0 }
            ],
            duration: 700,
            relative: true
        },

        nod_big: {
            keyframes: [
                { t: 0.0, angleY: 0 },
                { t: 0.3, angleY: -18 },
                { t: 0.6, angleY: 0 },
                { t: 1.0, angleY: 0 }
            ],
            duration: 800,
            relative: true
        },

        // === HEAD SHAKES ===
        shake: {
            keyframes: [
                { t: 0.0, angleX: 0 },
                { t: 0.15, angleX: 12 },
                { t: 0.35, angleX: -12 },
                { t: 0.55, angleX: 8 },
                { t: 0.75, angleX: -5 },
                { t: 1.0, angleX: 0 }
            ],
            duration: 700,
            relative: true
        },

        shake_slow: {
            keyframes: [
                { t: 0.0, angleX: 0 },
                { t: 0.2, angleX: 15 },
                { t: 0.5, angleX: -15 },
                { t: 0.8, angleX: 8 },
                { t: 1.0, angleX: 0 }
            ],
            duration: 1200,
            relative: true
        },

        shake_fast: {
            keyframes: [
                { t: 0.0, angleX: 0 },
                { t: 0.1, angleX: 10 },
                { t: 0.25, angleX: -10 },
                { t: 0.4, angleX: 8 },
                { t: 0.55, angleX: -6 },
                { t: 0.7, angleX: 4 },
                { t: 1.0, angleX: 0 }
            ],
            duration: 500,
            relative: true
        },

        shake_small: {
            keyframes: [
                { t: 0.0, angleX: 0 },
                { t: 0.2, angleX: 5 },
                { t: 0.4, angleX: -5 },
                { t: 0.6, angleX: 3 },
                { t: 1.0, angleX: 0 }
            ],
            duration: 500,
            relative: true
        },

        // === HEAD TURNS (big angleZ movement -30 to 30) ===
        head_turn_left: {
            keyframes: [
                { t: 0.0, angleZ: 0, angleX: 0 },
                { t: 0.3, angleZ: 25, angleX: -5 },
                { t: 0.6, angleZ: 30, angleX: -8 },
                { t: 0.8, angleZ: 20, angleX: -3 },
                { t: 1.0, angleZ: 0, angleX: 0 }
            ],
            duration: 2500,
            relative: true
        },

        head_turn_right: {
            keyframes: [
                { t: 0.0, angleZ: 0, angleX: 0 },
                { t: 0.3, angleZ: -25, angleX: 5 },
                { t: 0.6, angleZ: -30, angleX: 8 },
                { t: 0.8, angleZ: -20, angleX: 3 },
                { t: 1.0, angleZ: 0, angleX: 0 }
            ],
            duration: 2500,
            relative: true
        },

        // Random look around - combines head turn with eye movement
        look_around: {
            keyframes: [
                { t: 0.0, angleZ: 0, angleX: 0, eyeBallX: 0 },
                { t: 0.2, angleZ: 15, angleX: -8, eyeBallX: -0.4 },
                { t: 0.5, angleZ: -15, angleX: 8, eyeBallX: 0.4 },
                { t: 0.8, angleZ: 5, angleX: -3, eyeBallX: -0.1 },
                { t: 1.0, angleZ: 0, angleX: 0, eyeBallX: 0 }
            ],
            duration: 3000,
            relative: true
        },

        // === HEAD TILTS ===
        tilt: {
            keyframes: [
                { t: 0.0, angleZ: 0 },
                { t: 0.3, angleZ: 15 },
                { t: 0.7, angleZ: 15 },
                { t: 1.0, angleZ: 0 }
            ],
            duration: 1000,
            relative: true
        },

        tilt_left: {
            keyframes: [
                { t: 0.0, angleZ: 0 },
                { t: 0.3, angleZ: 18 },
                { t: 0.7, angleZ: 18 },
                { t: 1.0, angleZ: 0 }
            ],
            duration: 1200,
            relative: true
        },

        tilt_right: {
            keyframes: [
                { t: 0.0, angleZ: 0 },
                { t: 0.3, angleZ: -18 },
                { t: 0.7, angleZ: -18 },
                { t: 1.0, angleZ: 0 }
            ],
            duration: 1200,
            relative: true
        },

        tilt_curious: {
            keyframes: [
                { t: 0.0, angleZ: 0, browLY: 0, browRY: 0 },
                { t: 0.3, angleZ: 20, browLY: 0.3, browRY: 0.2 },
                { t: 0.7, angleZ: 20, browLY: 0.3, browRY: 0.2 },
                { t: 1.0, angleZ: 0, browLY: 0, browRY: 0 }
            ],
            duration: 1500,
            relative: true
        },

        // === EYE MOVEMENTS ===
        blink: {
            keyframes: [
                { t: 0.0, eyeOpenL: 0, eyeOpenR: 0 },
                { t: 0.3, eyeOpenL: -1, eyeOpenR: -1 },
                { t: 1.0, eyeOpenL: 0, eyeOpenR: 0 }
            ],
            duration: 200,
            relative: true
        },

        blink_slow: {
            keyframes: [
                { t: 0.0, eyeOpenL: 0, eyeOpenR: 0 },
                { t: 0.3, eyeOpenL: -1, eyeOpenR: -1 },
                { t: 0.6, eyeOpenL: -1, eyeOpenR: -1 },
                { t: 1.0, eyeOpenL: 0, eyeOpenR: 0 }
            ],
            duration: 500,
            relative: true
        },

        wink: {
            keyframes: [
                { t: 0.0, eyeOpenL: 0 },
                { t: 0.2, eyeOpenL: -0.9 },
                { t: 0.6, eyeOpenL: -0.9 },
                { t: 1.0, eyeOpenL: 0 }
            ],
            duration: 400,
            relative: true
        },

        wink_right: {
            keyframes: [
                { t: 0.0, eyeOpenR: 0 },
                { t: 0.2, eyeOpenR: -0.9 },
                { t: 0.6, eyeOpenR: -0.9 },
                { t: 1.0, eyeOpenR: 0 }
            ],
            duration: 400,
            relative: true
        },

        eye_roll: {
            keyframes: [
                { t: 0.0, eyeBallX: 0, eyeBallY: 0 },
                { t: 0.25, eyeBallX: 0.5, eyeBallY: -0.5 },
                { t: 0.5, eyeBallX: 0, eyeBallY: -0.7 },
                { t: 0.75, eyeBallX: -0.5, eyeBallY: -0.5 },
                { t: 1.0, eyeBallX: 0, eyeBallY: 0 }
            ],
            duration: 800,
            relative: true
        },

        look_left: {
            keyframes: [
                { t: 0.0, eyeBallX: 0, angleX: 0 },
                { t: 0.2, eyeBallX: -0.7, angleX: -5 },
                { t: 0.7, eyeBallX: -0.7, angleX: -5 },
                { t: 1.0, eyeBallX: 0, angleX: 0 }
            ],
            duration: 1200,
            relative: true
        },

        look_right: {
            keyframes: [
                { t: 0.0, eyeBallX: 0, angleX: 0 },
                { t: 0.2, eyeBallX: 0.7, angleX: 5 },
                { t: 0.7, eyeBallX: 0.7, angleX: 5 },
                { t: 1.0, eyeBallX: 0, angleX: 0 }
            ],
            duration: 1200,
            relative: true
        },

        look_up: {
            keyframes: [
                { t: 0.0, eyeBallY: 0, angleY: 0 },
                { t: 0.2, eyeBallY: 0.5, angleY: 8 },
                { t: 0.7, eyeBallY: 0.5, angleY: 8 },
                { t: 1.0, eyeBallY: 0, angleY: 0 }
            ],
            duration: 1000,
            relative: true
        },

        look_down: {
            keyframes: [
                { t: 0.0, eyeBallY: 0, angleY: 0 },
                { t: 0.2, eyeBallY: -0.5, angleY: -8 },
                { t: 0.7, eyeBallY: -0.5, angleY: -8 },
                { t: 1.0, eyeBallY: 0, angleY: 0 }
            ],
            duration: 1000,
            relative: true
        },

        look_away: {
            keyframes: [
                { t: 0.0, eyeBallX: 0, angleX: 0, angleZ: 0 },
                { t: 0.25, eyeBallX: 0.6, angleX: 8, angleZ: -5 },
                { t: 0.65, eyeBallX: 0.6, angleX: 8, angleZ: -5 },
                { t: 1.0, eyeBallX: 0, angleX: 0, angleZ: 0 }
            ],
            duration: 1500,
            relative: true
        },

        glance_left: {
            keyframes: [
                { t: 0.0, eyeBallX: 0 },
                { t: 0.15, eyeBallX: -0.6 },
                { t: 0.4, eyeBallX: -0.6 },
                { t: 0.6, eyeBallX: 0 },
                { t: 1.0, eyeBallX: 0 }
            ],
            duration: 600,
            relative: true
        },

        glance_right: {
            keyframes: [
                { t: 0.0, eyeBallX: 0 },
                { t: 0.15, eyeBallX: 0.6 },
                { t: 0.4, eyeBallX: 0.6 },
                { t: 0.6, eyeBallX: 0 },
                { t: 1.0, eyeBallX: 0 }
            ],
            duration: 600,
            relative: true
        },

        // === EYEBROW MOVEMENTS ===
        raise_brows: {
            keyframes: [
                { t: 0.0, browLY: 0, browRY: 0, eyeOpenL: 0, eyeOpenR: 0 },
                { t: 0.2, browLY: 0.5, browRY: 0.5, eyeOpenL: 0.2, eyeOpenR: 0.2 },
                { t: 0.7, browLY: 0.5, browRY: 0.5, eyeOpenL: 0.2, eyeOpenR: 0.2 },
                { t: 1.0, browLY: 0, browRY: 0, eyeOpenL: 0, eyeOpenR: 0 }
            ],
            duration: 800,
            relative: true
        },

        raise_brow_left: {
            keyframes: [
                { t: 0.0, browLY: 0 },
                { t: 0.2, browLY: 0.6 },
                { t: 0.7, browLY: 0.6 },
                { t: 1.0, browLY: 0 }
            ],
            duration: 800,
            relative: true
        },

        raise_brow_right: {
            keyframes: [
                { t: 0.0, browRY: 0 },
                { t: 0.2, browRY: 0.6 },
                { t: 0.7, browRY: 0.6 },
                { t: 1.0, browRY: 0 }
            ],
            duration: 800,
            relative: true
        },

        furrow_brows: {
            keyframes: [
                { t: 0.0, browLY: 0, browRY: 0 },
                { t: 0.2, browLY: -0.4, browRY: -0.4 },
                { t: 0.7, browLY: -0.4, browRY: -0.4 },
                { t: 1.0, browLY: 0, browRY: 0 }
            ],
            duration: 900,
            relative: true
        },

        // === BODY MOVEMENTS ===
        lean_in: {
            keyframes: [
                { t: 0.0, angleY: 0, bodyAngleY: 0 },
                { t: 0.3, angleY: -5, bodyAngleY: -3 },
                { t: 0.7, angleY: -5, bodyAngleY: -3 },
                { t: 1.0, angleY: 0, bodyAngleY: 0 }
            ],
            duration: 1200,
            relative: true
        },

        lean_back: {
            keyframes: [
                { t: 0.0, angleY: 0, bodyAngleY: 0 },
                { t: 0.3, angleY: 5, bodyAngleY: 3 },
                { t: 0.7, angleY: 5, bodyAngleY: 3 },
                { t: 1.0, angleY: 0, bodyAngleY: 0 }
            ],
            duration: 1200,
            relative: true
        },

        shrug: {
            keyframes: [
                { t: 0.0, angleZ: 0, browLY: 0, browRY: 0, bodyAngleZ: 0 },
                { t: 0.2, angleZ: 8, browLY: 0.4, browRY: 0.4, bodyAngleZ: 3 },
                { t: 0.6, angleZ: 8, browLY: 0.4, browRY: 0.4, bodyAngleZ: 3 },
                { t: 1.0, angleZ: 0, browLY: 0, browRY: 0, bodyAngleZ: 0 }
            ],
            duration: 900,
            relative: true
        },

        ponder: {
            keyframes: [
                { t: 0.0, angleX: 0, angleY: 0, eyeBallX: 0, eyeBallY: 0 },
                { t: 0.2, angleX: -10, angleY: 8, eyeBallX: -0.4, eyeBallY: 0.3 },
                { t: 0.8, angleX: -10, angleY: 8, eyeBallX: -0.4, eyeBallY: 0.3 },
                { t: 1.0, angleX: 0, angleY: 0, eyeBallX: 0, eyeBallY: 0 }
            ],
            duration: 2000,
            relative: true
        },

        sway: {
            keyframes: [
                { t: 0.0, bodyAngleX: 0 },
                { t: 0.25, bodyAngleX: 5 },
                { t: 0.75, bodyAngleX: -5 },
                { t: 1.0, bodyAngleX: 0 }
            ],
            duration: 1500,
            relative: true
        },

        lean_left: {
            keyframes: [
                { t: 0.0, bodyAngleX: 0, angleZ: 0 },
                { t: 0.3, bodyAngleX: 8, angleZ: 5 },
                { t: 0.7, bodyAngleX: 8, angleZ: 5 },
                { t: 1.0, bodyAngleX: 0, angleZ: 0 }
            ],
            duration: 1000,
            relative: true
        },

        lean_right: {
            keyframes: [
                { t: 0.0, bodyAngleX: 0, angleZ: 0 },
                { t: 0.3, bodyAngleX: -8, angleZ: -5 },
                { t: 0.7, bodyAngleX: -8, angleZ: -5 },
                { t: 1.0, bodyAngleX: 0, angleZ: 0 }
            ],
            duration: 1000,
            relative: true
        },

        sway_talk: {
            keyframes: [
                { t: 0.0, bodyAngleX: 0, angleZ: 0 },
                { t: 0.2, bodyAngleX: 4, angleZ: 3 },
                { t: 0.5, bodyAngleX: -4, angleZ: -3 },
                { t: 0.8, bodyAngleX: 3, angleZ: 2 },
                { t: 1.0, bodyAngleX: 0, angleZ: 0 }
            ],
            duration: 2000,
            relative: true
        },

        // Subtle idle sway - gentle head tilt for natural idle movement
        idle_sway: {
            keyframes: [
                { t: 0.0, angleZ: 0, angleY: 0 },
                { t: 0.25, angleZ: 3, angleY: -2 },
                { t: 0.5, angleZ: 0, angleY: 0 },
                { t: 0.75, angleZ: -3, angleY: 2 },
                { t: 1.0, angleZ: 0, angleY: 0 }
            ],
            duration: 4000,
            relative: true
        },

        // Very subtle breathing-like movement
        idle_breathe: {
            keyframes: [
                { t: 0.0, angleY: 0, bodyAngleY: 0 },
                { t: 0.5, angleY: 2, bodyAngleY: 1 },
                { t: 1.0, angleY: 0, bodyAngleY: 0 }
            ],
            duration: 3000,
            relative: true
        },

        bounce: {
            keyframes: [
                { t: 0.0, bodyAngleY: 0 },
                { t: 0.15, bodyAngleY: -5 },
                { t: 0.3, bodyAngleY: 0 },
                { t: 0.45, bodyAngleY: -4 },
                { t: 0.6, bodyAngleY: 0 },
                { t: 0.75, bodyAngleY: -2 },
                { t: 1.0, bodyAngleY: 0 }
            ],
            duration: 600,
            relative: true
        },

        // === HAND/ARM GESTURES ===
        // Model has TWO arm layers:
        //   armLB/armRB (Lift): -1=crossed, 0-5=raising up (the "crossed/raised" arm)
        //   armLA/armRA (Rot): -1=behind, 1=front (the "waist/thigh" arm)

        wave: {
            // Wave - armLB (left arm) + handChangeR (right hand param controls this arm's hand)
            // armLB: 5 = fully raised, handChangeR: 1 = open hand
            keyframes: [
                { t: 0.0, armLB: -1, armLA: -1, handChangeR: 0, handAngleR: 0 },
                { t: 0.15, armLB: 5, armLA: -1, handChangeR: 1, handAngleR: 0.5 },
                { t: 0.25, armLB: 5, armLA: -1, handChangeR: 1, handAngleR: -0.5 },
                { t: 0.35, armLB: 5, armLA: -1, handChangeR: 1, handAngleR: 0.5 },
                { t: 0.45, armLB: 5, armLA: -1, handChangeR: 1, handAngleR: -0.5 },
                { t: 0.55, armLB: 5, armLA: -1, handChangeR: 1, handAngleR: 0.5 },
                { t: 0.7, armLB: 5, armLA: -1, handChangeR: 1, handAngleR: 0 },
                { t: 0.85, armLB: 2, armLA: -1, handChangeR: 0.5, handAngleR: 0 },
                { t: 1.0, armLB: -1, armLA: -1, handChangeR: 0, handAngleR: 0 }
            ],
            duration: 1400,
            relative: false
        },

        wave_small: {
            // Smaller wave - armLB + handChangeR
            keyframes: [
                { t: 0.0, armLB: -1, armLA: -1, handChangeR: 0, handAngleR: 0 },
                { t: 0.2, armLB: 3, armLA: -1, handChangeR: 1, handAngleR: 0.3 },
                { t: 0.35, armLB: 3, armLA: -1, handChangeR: 1, handAngleR: -0.3 },
                { t: 0.5, armLB: 3, armLA: -1, handChangeR: 1, handAngleR: 0.3 },
                { t: 0.65, armLB: 3, armLA: -1, handChangeR: 1, handAngleR: -0.3 },
                { t: 0.8, armLB: 1.5, armLA: -1, handChangeR: 0.5, handAngleR: 0 },
                { t: 1.0, armLB: -1, armLA: -1, handChangeR: 0, handAngleR: 0 }
            ],
            duration: 1000,
            relative: false
        },

        point: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1 },
                { t: 0.3, armRB: 2, armRA: -1 },
                { t: 0.7, armRB: 2, armRA: -1 },
                { t: 1.0, armRB: -1, armRA: -1 }
            ],
            duration: 1200,
            relative: false
        },

        hands_up: {
            // Both hands up with open palms
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.3, armLB: 4, armRB: 4, armLA: -1, armRA: -1, handChangeL: 1, handChangeR: 1 },
                { t: 0.7, armLB: 4, armRB: 4, armLA: -1, armRA: -1, handChangeL: 1, handChangeR: 1 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1200,
            relative: false
        },

        clap: {
            // Clapping with both hands - hands come together
            // handChangeL/R: 0.5 = flat palm for clapping
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.1, armLB: 1.5, armRB: 1.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0.5 },
                { t: 0.2, armLB: 1, armRB: 1, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0.5 },
                { t: 0.3, armLB: 1.5, armRB: 1.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0.5 },
                { t: 0.4, armLB: 1, armRB: 1, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0.5 },
                { t: 0.5, armLB: 1.5, armRB: 1.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0.5 },
                { t: 0.65, armLB: 0.5, armRB: 0.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0.5 },
                { t: 0.8, armLB: 0, armRB: 0, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1200,
            relative: false
        },

        thumbs_up: {
            // Thumbs up with hand pose change
            // armRB uses handChangeL
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, handChangeL: 0 },
                { t: 0.25, armRB: 2, armRA: -1, handChangeL: 1 },
                { t: 0.7, armRB: 2, armRA: -1, handChangeL: 1 },
                { t: 1.0, armRB: -1, armRA: -1, handChangeL: 0 }
            ],
            duration: 1200,
            relative: false
        },

        facepalm: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, angleY: 0 },
                { t: 0.3, armRB: 4, armRA: -1, angleY: 8 },
                { t: 0.7, armRB: 4, armRA: -1, angleY: 8 },
                { t: 1.0, armRB: -1, armRA: -1, angleY: 0 }
            ],
            duration: 1500,
            relative: false
        },

        arms_crossed: {
            // Both crossed arms visible, waist arms hidden
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1 },
                { t: 0.3, armLB: -1, armRB: -1, armLA: -1, armRA: -1 },
                { t: 0.7, armLB: -1, armRB: -1, armLA: -1, armRA: -1 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1 }
            ],
            duration: 1000,
            relative: false
        },

        hand_on_chest: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1 },
                { t: 0.3, armRB: 0.5, armRA: -1 },
                { t: 0.7, armRB: 0.5, armRA: -1 },
                { t: 1.0, armRB: -1, armRA: -1 }
            ],
            duration: 1200,
            relative: false
        },

        // Waist arm gestures (using A params)
        // These show the waist arm layer, so hide the raised arm layer (B=-1)
        arm_behind: {
            keyframes: [
                { t: 0.0, armRA: 0, armRB: -1 },
                { t: 0.3, armRA: -1, armRB: -1 },
                { t: 0.7, armRA: -1, armRB: -1 },
                { t: 1.0, armRA: 0, armRB: -1 }
            ],
            duration: 1000,
            relative: false
        },

        arm_forward: {
            keyframes: [
                { t: 0.0, armRA: 0, armRB: -1 },
                { t: 0.3, armRA: 1, armRB: -1 },
                { t: 0.7, armRA: 1, armRB: -1 },
                { t: 1.0, armRA: 0, armRB: -1 }
            ],
            duration: 1000,
            relative: false
        },

        // === PRESENTATION / SPEAKING GESTURES ===
        // Natural gestures for when LLM is speaking/explaining
        // NOTE: Arm/Hand mapping: armLB uses handChangeR, armRB uses handChangeL

        // Open hand presenting - explaining something
        present: {
            // armLB: 3.8, armRB: 5.0, handL: 0, handR: 0.5
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.2, armLB: 3.8, armRB: 5.0, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.7, armLB: 3.8, armRB: 5.0, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1500,
            relative: false
        },

        // Both hands open - welcoming or explaining broadly
        // armLB: 2.70, armRB: 2.70, handL: 0.5, handR: 0
        present_both: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.2, armLB: 2.7, armRB: 2.7, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.7, armLB: 2.7, armRB: 2.7, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1800,
            relative: false
        },

        // Air quotes gesture
        air_quotes: {
            // armLB: 3.8, armRB: 3.8, handL: 0, handR: 0.5
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.15, armLB: 3.8, armRB: 3.8, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.25, armLB: 3.5, armRB: 3.5, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.35, armLB: 3.8, armRB: 3.8, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.5, armLB: 3.5, armRB: 3.5, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.7, armLB: 2, armRB: 2, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1200,
            relative: false
        },

        // Thinking with hand near chin
        // armRB uses handChangeL
        think_hand: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, handChangeL: 0, angleX: 0, angleY: 0 },
                { t: 0.25, armRB: 3.5, armRA: -1, handChangeL: 0.5, angleX: -8, angleY: 5 },
                { t: 0.7, armRB: 3.5, armRA: -1, handChangeL: 0.5, angleX: -8, angleY: 5 },
                { t: 1.0, armRB: -1, armRA: -1, handChangeL: 0, angleX: 0, angleY: 0 }
            ],
            duration: 2000,
            relative: false
        },

        // Making a point - single raised finger/hand
        // armRB uses handChangeL
        make_point: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, handChangeL: 0 },
                { t: 0.15, armRB: 2, armRA: -1, handChangeL: 1 },
                { t: 0.25, armRB: 2.3, armRA: -1, handChangeL: 1 },
                { t: 0.5, armRB: 2, armRA: -1, handChangeL: 1 },
                { t: 0.7, armRB: 1.5, armRA: -1, handChangeL: 0.5 },
                { t: 1.0, armRB: -1, armRA: -1, handChangeL: 0 }
            ],
            duration: 1200,
            relative: false
        },

        // Emphasize with hand movement
        emphasize: {
            // armLB: 0.7, armRB: 3.2, handL: 0, handR: 0.5
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.1, armLB: 0.7, armRB: 3.2, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.2, armLB: 1.0, armRB: 3.5, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.35, armLB: 0.7, armRB: 3.2, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.5, armLB: 1.0, armRB: 3.5, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 0.7, armLB: 0.5, armRB: 2.5, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1000,
            relative: false
        },

        // Listing/counting gesture - small movements
        // armRB uses handChangeL
        listing: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, handChangeL: 0 },
                { t: 0.1, armRB: 1.2, armRA: -1, handChangeL: 0.5 },
                { t: 0.25, armRB: 1.5, armRA: -1, handChangeL: 0.5 },
                { t: 0.4, armRB: 1.2, armRA: -1, handChangeL: 1 },
                { t: 0.55, armRB: 1.5, armRA: -1, handChangeL: 1 },
                { t: 0.7, armRB: 1.2, armRA: -1, handChangeL: 0.5 },
                { t: 1.0, armRB: -1, armRA: -1, handChangeL: 0 }
            ],
            duration: 1400,
            relative: false
        },

        // Welcoming/inviting gesture
        // armLB: 5.0, armRB: 1.6, handL: 0.5, handR: 1.0
        // Waving motion on armLB
        welcome: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0, angleX: 0 },
                { t: 0.15, armLB: 5.0, armRB: 1.6, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 1, angleX: 5 },
                { t: 0.3, armLB: 4.5, armRB: 1.6, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 1, angleX: 5 },
                { t: 0.45, armLB: 5.0, armRB: 1.6, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 1, angleX: 5 },
                { t: 0.6, armLB: 4.5, armRB: 1.6, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 1, angleX: 3 },
                { t: 0.75, armLB: 5.0, armRB: 1.6, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 1, angleX: 3 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0, angleX: 0 }
            ],
            duration: 1600,
            relative: false
        },

        // Dismissive wave - "no no"
        // armRB uses handChangeL
        dismiss_hand: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, handChangeL: 0, handAngleL: 0 },
                { t: 0.15, armRB: 2, armRA: -1, handChangeL: 1, handAngleL: 0.5 },
                { t: 0.3, armRB: 2, armRA: -1, handChangeL: 1, handAngleL: -0.5 },
                { t: 0.45, armRB: 2, armRA: -1, handChangeL: 1, handAngleL: 0.5 },
                { t: 0.6, armRB: 2, armRA: -1, handChangeL: 1, handAngleL: -0.3 },
                { t: 0.8, armRB: 1, armRA: -1, handChangeL: 0.5, handAngleL: 0 },
                { t: 1.0, armRB: -1, armRA: -1, handChangeL: 0, handAngleL: 0 }
            ],
            duration: 1200,
            relative: false
        },

        // Sincere hand on chest
        // armLB: 3.30, armRB: 3.30, handL: 0.50, handR: 0
        sincere: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0, angleY: 0 },
                { t: 0.2, armLB: 3.3, armRB: 3.3, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0, angleY: -3 },
                { t: 0.7, armLB: 3.3, armRB: 3.3, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0, angleY: -3 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0, angleY: 0 }
            ],
            duration: 1500,
            relative: false
        },

        // Questioning gesture - palm up
        // armLB: 2.8, armRB: -1, handL: 0, handR: 0.5
        // armLB uses handChangeR
        question_hand: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0, angleZ: 0 },
                { t: 0.2, armLB: 2.8, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5, angleZ: 8 },
                { t: 0.6, armLB: 2.8, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5, angleZ: 10 },
                { t: 0.8, armLB: 2.8, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0.5, angleZ: 8 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0, angleZ: 0 }
            ],
            duration: 1400,
            relative: false
        },

        // Calm down gesture - both hands lowering
        // armLB: 2.10, armRB: 0.50, handL: 0.50, handR: 0
        calm_down: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.2, armLB: 2.1, armRB: 0.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.4, armLB: 1.8, armRB: 0.3, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.6, armLB: 1.5, armRB: 0.1, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.8, armLB: 1.0, armRB: -0.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1600,
            relative: false
        },

        // Small acknowledgment hand raise
        // armLB: -0.50, armRB: 2.80, handL: 0.50, handR: 0
        acknowledge_hand: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.2, armLB: -0.5, armRB: 2.8, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.5, armLB: -0.5, armRB: 3.0, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.7, armLB: -0.5, armRB: 2.8, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1000,
            relative: false
        },

        // Excited hand gesture
        // armLB: 5.0, armRB: 5.0, handL: 0.5, handR: 0
        excited_hands: {
            keyframes: [
                { t: 0.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 },
                { t: 0.1, armLB: 4.5, armRB: 4.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.2, armLB: 5.0, armRB: 5.0, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.35, armLB: 4.5, armRB: 4.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.5, armLB: 5.0, armRB: 5.0, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 0.7, armLB: 3.5, armRB: 3.5, armLA: -1, armRA: -1, handChangeL: 0.5, handChangeR: 0 },
                { t: 1.0, armLB: -1, armRB: -1, armLA: -1, armRA: -1, handChangeL: 0, handChangeR: 0 }
            ],
            duration: 1200,
            relative: false
        },

        // === COMPLEX COMBINED GESTURES ===
        laugh: {
            keyframes: [
                { t: 0.0, mouthOpen: 0, angleY: 0, eyeOpenL: 0, eyeOpenR: 0 },
                { t: 0.1, mouthOpen: 0.4, angleY: -3, eyeOpenL: -0.2, eyeOpenR: -0.2 },
                { t: 0.2, mouthOpen: 0.2, angleY: 0, eyeOpenL: -0.1, eyeOpenR: -0.1 },
                { t: 0.3, mouthOpen: 0.5, angleY: -3, eyeOpenL: -0.2, eyeOpenR: -0.2 },
                { t: 0.4, mouthOpen: 0.2, angleY: 0, eyeOpenL: -0.1, eyeOpenR: -0.1 },
                { t: 0.5, mouthOpen: 0.4, angleY: -2, eyeOpenL: -0.2, eyeOpenR: -0.2 },
                { t: 0.7, mouthOpen: 0.2, angleY: 0, eyeOpenL: -0.1, eyeOpenR: -0.1 },
                { t: 1.0, mouthOpen: 0, angleY: 0, eyeOpenL: 0, eyeOpenR: 0 }
            ],
            duration: 1200,
            relative: true
        },

        gasp: {
            keyframes: [
                { t: 0.0, mouthOpen: 0, eyeOpenL: 0, eyeOpenR: 0, browLY: 0, browRY: 0 },
                { t: 0.15, mouthOpen: 0.6, eyeOpenL: 0.3, eyeOpenR: 0.3, browLY: 0.5, browRY: 0.5 },
                { t: 0.6, mouthOpen: 0.5, eyeOpenL: 0.3, eyeOpenR: 0.3, browLY: 0.5, browRY: 0.5 },
                { t: 1.0, mouthOpen: 0, eyeOpenL: 0, eyeOpenR: 0, browLY: 0, browRY: 0 }
            ],
            duration: 1000,
            relative: true
        },

        sigh: {
            keyframes: [
                { t: 0.0, angleY: 0, eyeOpenL: 0, eyeOpenR: 0, mouthOpen: 0 },
                { t: 0.2, angleY: 5, eyeOpenL: -0.3, eyeOpenR: -0.3, mouthOpen: 0.2 },
                { t: 0.5, angleY: 8, eyeOpenL: -0.3, eyeOpenR: -0.3, mouthOpen: 0.3 },
                { t: 0.8, angleY: 5, eyeOpenL: -0.2, eyeOpenR: -0.2, mouthOpen: 0.1 },
                { t: 1.0, angleY: 0, eyeOpenL: 0, eyeOpenR: 0, mouthOpen: 0 }
            ],
            duration: 1500,
            relative: true
        },

        startle: {
            keyframes: [
                { t: 0.0, angleY: 0, eyeOpenL: 0, eyeOpenR: 0, browLY: 0, browRY: 0, bodyAngleY: 0 },
                { t: 0.1, angleY: -8, eyeOpenL: 0.4, eyeOpenR: 0.4, browLY: 0.6, browRY: 0.6, bodyAngleY: -3 },
                { t: 0.4, angleY: -5, eyeOpenL: 0.3, eyeOpenR: 0.3, browLY: 0.5, browRY: 0.5, bodyAngleY: -2 },
                { t: 1.0, angleY: 0, eyeOpenL: 0, eyeOpenR: 0, browLY: 0, browRY: 0, bodyAngleY: 0 }
            ],
            duration: 800,
            relative: true
        },

        double_take: {
            keyframes: [
                { t: 0.0, angleX: 0, eyeBallX: 0 },
                { t: 0.15, angleX: 10, eyeBallX: 0.5 },
                { t: 0.3, angleX: 0, eyeBallX: 0 },
                { t: 0.4, angleX: 15, eyeBallX: 0.7, eyeOpenL: 0.2, eyeOpenR: 0.2 },
                { t: 0.7, angleX: 15, eyeBallX: 0.7, eyeOpenL: 0.2, eyeOpenR: 0.2 },
                { t: 1.0, angleX: 0, eyeBallX: 0, eyeOpenL: 0, eyeOpenR: 0 }
            ],
            duration: 1200,
            relative: true
        },

        // === NAVIGATION GESTURES ===
        // Point right + look right - triggers "next" navigation
        nav_next: {
            keyframes: [
                { t: 0.0, armRB: -1, armRA: -1, angleX: 0, eyeBallX: 0 },
                { t: 0.2, armRB: 3, armRA: -1, angleX: 15, eyeBallX: 0.5 },
                { t: 0.5, armRB: 3.5, armRA: -1, angleX: 18, eyeBallX: 0.6 },
                { t: 0.7, armRB: 3, armRA: -1, angleX: 15, eyeBallX: 0.5 },
                { t: 1.0, armRB: -1, armRA: -1, angleX: 0, eyeBallX: 0 }
            ],
            duration: 1200,
            relative: false,
            triggerNavigation: 'next'  // Triggers navigation event on completion
        },

        // Point left + look left - triggers "back" navigation
        nav_back: {
            keyframes: [
                { t: 0.0, armLB: -1, armLA: -1, angleX: 0, eyeBallX: 0 },
                { t: 0.2, armLB: 3, armLA: -1, angleX: -15, eyeBallX: -0.5 },
                { t: 0.5, armLB: 3.5, armLA: -1, angleX: -18, eyeBallX: -0.6 },
                { t: 0.7, armLB: 3, armLA: -1, angleX: -15, eyeBallX: -0.5 },
                { t: 1.0, armLB: -1, armLA: -1, angleX: 0, eyeBallX: 0 }
            ],
            duration: 1200,
            relative: false,
            triggerNavigation: 'back'  // Triggers navigation event on completion
        }
    },

    // ============================================
    // EYE - Quick eye action aliases for LLM
    // Usage: [eye:wink], [eye:lookup], [eye:roll]
    // ============================================
    eye: {
        blink: 'blink',
        blink_slow: 'blink_slow',
        wink: 'wink',
        wink_left: 'wink',
        wink_right: 'wink_right',
        roll: 'eye_roll',
        lookup: 'look_up',
        look_up: 'look_up',
        lookdown: 'look_down',
        look_down: 'look_down',
        left: 'look_left',
        look_left: 'look_left',
        right: 'look_right',
        look_right: 'look_right',
        away: 'look_away',
        look_away: 'look_away',
        glance_left: 'glance_left',
        glance_right: 'glance_right'
    },

    // ============================================
    // HEAD - Quick head action aliases for LLM
    // Usage: [head:nod], [head:shake], [head:tilt]
    // ============================================
    head: {
        nod: 'nod',
        nod_slow: 'nod_slow',
        nod_fast: 'nod_fast',
        nod_double: 'nod_double',
        nod_big: 'nod_big',
        shake: 'shake',
        shake_slow: 'shake_slow',
        shake_fast: 'shake_fast',
        shake_small: 'shake_small',
        tilt: 'tilt',
        tilt_left: 'tilt_left',
        tilt_right: 'tilt_right',
        tilt_curious: 'tilt_curious',
        curious: 'tilt_curious',
        turn_left: 'head_turn_left',    // Big head turn left (angleZ 30)
        turn_right: 'head_turn_right',  // Big head turn right (angleZ -30)
        look_around: 'look_around',     // Random look around
        lookup: 'look_up',              // Head tilts up (thinking)
        look_up: 'look_up',
        think: 'ponder',                // Thinking pose with head tilt
        ponder: 'ponder'
    },

    // ============================================
    // BODY - Quick body action aliases for LLM
    // Usage: [body:lean_in], [body:shrug], [body:bounce]
    // ============================================
    body: {
        lean: 'lean_in',
        lean_in: 'lean_in',
        lean_forward: 'lean_in',
        lean_back: 'lean_back',
        back: 'lean_back',
        lean_left: 'lean_left',
        left: 'lean_left',
        lean_right: 'lean_right',
        right: 'lean_right',
        shrug: 'shrug',
        ponder: 'ponder',
        sway: 'sway',
        sway_talk: 'sway_talk',
        talk: 'sway_talk',
        bounce: 'bounce',
        laugh: 'laugh',
        gasp: 'gasp',
        sigh: 'sigh',
        startle: 'startle'
    },

    // ============================================
    // BROW - Eyebrow action aliases for LLM
    // Usage: [brow:raise], [brow:furrow]
    // ============================================
    brow: {
        raise: 'raise_brows',
        raise_both: 'raise_brows',
        raise_left: 'raise_brow_left',
        raise_right: 'raise_brow_right',
        furrow: 'furrow_brows',
        frown: 'furrow_brows'
    },

    // ============================================
    // GESTURE - Direct gesture aliases for LLM
    // Usage: [gesture:nav_next], [gesture:wave]
    // ============================================
    gesture: {
        // Navigation gestures
        nav_next: 'nav_next',
        nav_back: 'nav_back',
        next: 'nav_next',
        back: 'nav_back',
        // Common gestures
        nod: 'nod',
        shake: 'shake',
        wave: 'wave',
        wink: 'wink',
        thumbs_up: 'thumbs_up',
        clap: 'clap',
        shrug: 'shrug',
        think: 'think_hand',
        present: 'present',
        point: 'point'
    },

    // ============================================
    // ACTIONS - Compound mood + gesture combinations
    // ============================================
    actions: {
        greet: { mood: 'friendly', gesture: 'nod' },
        greet_excited: { mood: 'excited', gesture: 'wave' },
        agree: { mood: 'happy', gesture: 'nod' },
        agree_strong: { mood: 'confident', gesture: 'nod_big' },
        disagree: { mood: 'serious', gesture: 'shake' },
        disagree_strong: { mood: 'annoyed', gesture: 'shake_fast' },
        confused: { mood: 'curious', gesture: 'tilt_curious' },
        consider: { mood: 'thinking', gesture: 'ponder' },
        emphasize: { mood: 'confident', gesture: 'lean_in' },
        unsure: { mood: 'concerned', gesture: 'shrug' },
        notice: { mood: 'surprised', gesture: 'raise_brows' },
        dismiss: { mood: 'skeptical', gesture: 'look_away' },
        acknowledge: { mood: 'neutral', gesture: 'nod' },
        celebrate: { mood: 'excited', gesture: 'bounce' },
        amuse: { mood: 'amused', gesture: 'laugh' },
        shock: { mood: 'surprised', gesture: 'gasp' },
        disappoint: { mood: 'sad', gesture: 'sigh' },
        doubt: { mood: 'skeptical', gesture: 'raise_brow_right' },
        flirt: { mood: 'mischievous', gesture: 'wink' },
        encourage: { mood: 'happy', gesture: 'thumbs_up' },
        frustrate: { mood: 'annoyed', gesture: 'facepalm' }
    }
};

/**
 * ActionLibrary class - Interface for accessing actions
 */
class ActionLibrary {
    constructor(customLibrary = null) {
        this.library = customLibrary || ACTION_LIBRARY;
    }

    getMood(name) {
        return this.library.moods[name.toLowerCase()] || null;
    }

    getGesture(name) {
        return this.library.gestures[name.toLowerCase()] || null;
    }

    getAction(name) {
        const action = this.library.actions[name.toLowerCase()];
        if (!action) return null;

        return {
            mood: action.mood ? this.getMood(action.mood) : null,
            moodName: action.mood,
            gesture: action.gesture ? this.getGesture(action.gesture) : null,
            gestureName: action.gesture
        };
    }

    get(type, name) {
        const lowerType = type.toLowerCase();
        const lowerName = name.toLowerCase();

        switch (lowerType) {
            case 'mood':
                return { type: 'mood', data: this.getMood(lowerName), name: lowerName };
            case 'gesture':
                return { type: 'gesture', data: this.getGesture(lowerName), name: lowerName };
            case 'action':
                return { type: 'action', data: this.getAction(lowerName), name: lowerName };
            // Alias categories - resolve to gestures
            case 'eye':
            case 'head':
            case 'body':
            case 'brow':
            case 'gesture': {
                const aliasMap = this.library[lowerType];
                if (aliasMap && aliasMap[lowerName]) {
                    const gestureName = aliasMap[lowerName];
                    return { type: 'gesture', data: this.getGesture(gestureName), name: gestureName, originalType: lowerType };
                }
                // For 'gesture' type, also try direct lookup in gestures
                if (lowerType === 'gesture') {
                    const directGesture = this.getGesture(lowerName);
                    if (directGesture) {
                        return { type: 'gesture', data: directGesture, name: lowerName, originalType: lowerType };
                    }
                }
                return null;
            }
            default:
                return null;
        }
    }

    list(type) {
        const category = this.library[type.toLowerCase()];
        return category ? Object.keys(category) : [];
    }

    has(type, name) {
        return !!this.get(type, name)?.data;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ActionLibrary, ACTION_LIBRARY };
}
