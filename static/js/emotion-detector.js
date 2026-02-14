/**
 * EmotionDetector - Detects emotion from text using keyword patterns
 * Used to automatically set avatar expressions based on co-host responses
 */

// Emotion definitions with parameter presets
const EMOTIONS = {
    neutral: {
        name: 'neutral',
        params: {
            angleX: 0, angleY: 0, angleZ: 0,
            mouthForm: 0,
            eyeOpenL: 1, eyeOpenR: 1,
            eyeBallX: 0, eyeBallY: 0,
            browLY: 0, browRY: 0
        },
        idleVariation: { angleX: 3, angleY: 2, angleZ: 2 }
    },
    happy: {
        name: 'happy',
        params: {
            angleX: 5, angleY: -3, angleZ: 5,
            mouthForm: 0.7,
            eyeOpenL: 0.75, eyeOpenR: 0.75,
            eyeBallX: 0, eyeBallY: -0.1,
            browLY: 0.2, browRY: 0.2
        },
        idleVariation: { angleX: 5, angleY: 3, angleZ: 4 }
    },
    excited: {
        name: 'excited',
        params: {
            angleX: 3, angleY: -5, angleZ: 8,
            mouthForm: 1,
            eyeOpenL: 1.1, eyeOpenR: 1.1,
            eyeBallX: 0, eyeBallY: -0.2,
            browLY: 0.5, browRY: 0.5
        },
        idleVariation: { angleX: 8, angleY: 5, angleZ: 6 }
    },
    thinking: {
        name: 'thinking',
        params: {
            angleX: -12, angleY: 8, angleZ: 6,
            mouthForm: 0.1,
            eyeOpenL: 0.85, eyeOpenR: 0.6,
            eyeBallX: 0.4, eyeBallY: -0.25,
            browLY: 0.15, browRY: -0.15
        },
        idleVariation: { angleX: 4, angleY: 3, angleZ: 2 }
    },
    surprised: {
        name: 'surprised',
        params: {
            angleX: 0, angleY: -8, angleZ: 0,
            mouthForm: 0,
            eyeOpenL: 1.25, eyeOpenR: 1.25,
            eyeBallX: 0, eyeBallY: 0,
            browLY: 0.6, browRY: 0.6
        },
        idleVariation: { angleX: 2, angleY: 2, angleZ: 1 }
    },
    skeptical: {
        name: 'skeptical',
        params: {
            angleX: -8, angleY: 5, angleZ: -5,
            mouthForm: -0.2,
            eyeOpenL: 0.7, eyeOpenR: 0.9,
            eyeBallX: 0.3, eyeBallY: 0.1,
            browLY: -0.3, browRY: 0.2
        },
        idleVariation: { angleX: 3, angleY: 2, angleZ: 2 }
    },
    sad: {
        name: 'sad',
        params: {
            angleX: -5, angleY: 12, angleZ: -3,
            mouthForm: -0.5,
            eyeOpenL: 0.6, eyeOpenR: 0.6,
            eyeBallX: -0.2, eyeBallY: 0.3,
            browLY: -0.4, browRY: -0.4
        },
        idleVariation: { angleX: 2, angleY: 2, angleZ: 1 }
    },
    confident: {
        name: 'confident',
        params: {
            angleX: 5, angleY: -5, angleZ: 3,
            mouthForm: 0.4,
            eyeOpenL: 0.9, eyeOpenR: 0.9,
            eyeBallX: 0, eyeBallY: -0.15,
            browLY: 0.1, browRY: 0.1
        },
        idleVariation: { angleX: 4, angleY: 3, angleZ: 3 }
    }
};

// Keyword patterns for emotion detection
const EMOTION_PATTERNS = {
    excited: [
        /[!]{2,}/,                           // Multiple exclamation marks
        /\b(amazing|awesome|wow|incredible|fantastic|brilliant)\b/i,
        /\b(love it|perfect|exactly)\b/i,
        /\b(yes!+)\b/i
    ],
    thinking: [
        /\b(hmm+|hm+|well)\b/i,
        /\b(let me think|thinking|consider|perhaps)\b/i,
        /\b(interesting|curious|wonder)\b/i,
        /\b(maybe|might|could be)\b/i,
        /^(so|now|okay)\b/i
    ],
    surprised: [
        /\b(oh!|whoa|what\?|really\?)\b/i,
        /\b(wait|hold on|seriously)\b/i,
        /\?!|\?{2,}/,                        // ?! or multiple ?
        /\b(unexpected|didn't expect)\b/i
    ],
    happy: [
        /\b(great|wonderful|excellent|happy|glad|pleased)\b/i,
        /\b(nice|good job|well done)\b/i,
        /\b(thank|appreciate)\b/i,
        /\b(fun|enjoy|like)\b/i
    ],
    skeptical: [
        /\b(but|however|although|though)\b/i,
        /\b(not sure|doubt|question)\b/i,
        /\b(really\?|are you sure)\b/i,
        /\b(actually|technically)\b/i
    ],
    sad: [
        /\b(sorry|unfortunately|sad|bad news)\b/i,
        /\b(regret|apologize|my bad)\b/i,
        /\b(disappointed|miss|lost)\b/i
    ],
    confident: [
        /\b(definitely|absolutely|certainly)\b/i,
        /\b(of course|obviously|clearly)\b/i,
        /\b(i know|trust me|believe me)\b/i
    ]
};

class EmotionDetector {
    constructor() {
        this.lastEmotion = 'neutral';
        this.emotionHistory = [];
        this.maxHistory = 5;
    }

    /**
     * Detect emotion from text
     * Returns emotion name string
     */
    detect(text) {
        if (!text || typeof text !== 'string') {
            return 'neutral';
        }

        const scores = {};

        // Score each emotion based on pattern matches
        for (const [emotion, patterns] of Object.entries(EMOTION_PATTERNS)) {
            scores[emotion] = 0;

            for (const pattern of patterns) {
                const matches = text.match(pattern);
                if (matches) {
                    // Weight by number of matches
                    scores[emotion] += matches.length;
                }
            }
        }

        // Find highest scoring emotion
        let maxScore = 0;
        let detectedEmotion = 'neutral';

        for (const [emotion, score] of Object.entries(scores)) {
            if (score > maxScore) {
                maxScore = score;
                detectedEmotion = emotion;
            }
        }

        // Only return non-neutral if we have a meaningful match
        if (maxScore < 1) {
            detectedEmotion = 'neutral';
        }

        // Track history
        this.emotionHistory.push(detectedEmotion);
        if (this.emotionHistory.length > this.maxHistory) {
            this.emotionHistory.shift();
        }

        this.lastEmotion = detectedEmotion;
        return detectedEmotion;
    }

    /**
     * Get emotion parameters for avatar
     */
    getEmotionParams(emotionName) {
        const emotion = EMOTIONS[emotionName] || EMOTIONS.neutral;
        return emotion.params;
    }

    /**
     * Get full emotion object
     */
    getEmotion(emotionName) {
        return EMOTIONS[emotionName] || EMOTIONS.neutral;
    }

    /**
     * Get all available emotion names
     */
    getEmotionNames() {
        return Object.keys(EMOTIONS);
    }

    /**
     * Get the most frequent recent emotion
     */
    getDominantEmotion() {
        if (this.emotionHistory.length === 0) {
            return 'neutral';
        }

        const counts = {};
        for (const emotion of this.emotionHistory) {
            counts[emotion] = (counts[emotion] || 0) + 1;
        }

        let maxCount = 0;
        let dominant = 'neutral';
        for (const [emotion, count] of Object.entries(counts)) {
            if (count > maxCount) {
                maxCount = count;
                dominant = emotion;
            }
        }

        return dominant;
    }

    /**
     * Clear emotion history
     */
    reset() {
        this.lastEmotion = 'neutral';
        this.emotionHistory = [];
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { EmotionDetector, EMOTIONS, EMOTION_PATTERNS };
}
