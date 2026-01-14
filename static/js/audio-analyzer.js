/**
 * AudioAnalyzer - Analyzes audio for lip sync
 * Uses Web Audio API to extract volume levels from audio playback
 */

class AudioAnalyzer {
    constructor() {
        this.audioContext = null;
        this.analyser = null;
        this.dataArray = null;
        this.connectedSources = new WeakMap(); // Track connected audio elements
        this.smoothedVolume = 0;
        this.smoothingFactor = 0.3; // Lower = smoother, higher = more responsive
        this.sensitivity = 1.5;
        this.threshold = 0.02; // Minimum volume to register
    }

    /**
     * Initialize the audio context
     */
    async init() {
        if (this.audioContext) return this;

        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.5;
        this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);

        // Connect analyser to destination so we can still hear the audio
        this.analyser.connect(this.audioContext.destination);

        return this;
    }

    /**
     * Resume audio context (required after user gesture)
     */
    async resume() {
        if (this.audioContext?.state === 'suspended') {
            await this.audioContext.resume();
        }
    }

    /**
     * Connect an Audio element to the analyzer
     */
    connectAudioElement(audioElement) {
        if (!this.audioContext || !audioElement) return false;

        // Check if already connected
        if (this.connectedSources.has(audioElement)) {
            return true;
        }

        try {
            const source = this.audioContext.createMediaElementSource(audioElement);
            source.connect(this.analyser);
            this.connectedSources.set(audioElement, source);
            return true;
        } catch (e) {
            // Element might already be connected to another context
            console.warn('[AudioAnalyzer] Could not connect audio element:', e.message);
            return false;
        }
    }

    /**
     * Connect a MediaStream to the analyzer (for microphone input)
     */
    connectStream(stream) {
        if (!this.audioContext) return false;

        try {
            const source = this.audioContext.createMediaStreamSource(stream);
            source.connect(this.analyser);
            return true;
        } catch (e) {
            console.warn('[AudioAnalyzer] Could not connect stream:', e.message);
            return false;
        }
    }

    /**
     * Get raw volume level (0-1)
     */
    getVolume() {
        if (!this.analyser) return 0;

        this.analyser.getByteFrequencyData(this.dataArray);

        // Focus on voice frequency range (roughly 85Hz - 3000Hz)
        // With fftSize=256 at 44100Hz, each bin is ~172Hz
        // Bins 0-1 are very low frequencies, bins 2-18 cover voice range
        let sum = 0;
        const voiceStart = 1;
        const voiceEnd = 20;

        for (let i = voiceStart; i < voiceEnd; i++) {
            sum += this.dataArray[i];
        }

        const average = sum / (voiceEnd - voiceStart);
        const normalized = average / 255;

        // Apply smoothing to prevent jitter
        this.smoothedVolume = this.smoothedVolume * this.smoothingFactor +
                              normalized * (1 - this.smoothingFactor);

        return this.smoothedVolume;
    }

    /**
     * Get mouth value for lip sync (0-1)
     * Applies sensitivity and curve for more natural movement
     */
    getMouthValue() {
        const volume = this.getVolume();

        // Apply threshold
        if (volume < this.threshold) {
            return 0;
        }

        // Apply curve for more natural movement
        // Power < 1 makes quiet sounds more visible
        const curved = Math.pow(volume, 0.7) * this.sensitivity;

        return Math.min(1, Math.max(0, curved));
    }

    /**
     * Get frequency data for more detailed analysis
     */
    getFrequencyData() {
        if (!this.analyser) return null;

        this.analyser.getByteFrequencyData(this.dataArray);
        return this.dataArray;
    }

    /**
     * Check if currently detecting audio
     */
    isActive() {
        return this.getVolume() > this.threshold;
    }

    /**
     * Set sensitivity (0.5 - 3.0 recommended)
     */
    setSensitivity(value) {
        this.sensitivity = Math.max(0.1, Math.min(5, value));
    }

    /**
     * Set smoothing factor (0 = no smoothing, 1 = maximum smoothing)
     */
    setSmoothing(value) {
        this.smoothingFactor = Math.max(0, Math.min(0.95, value));
    }

    /**
     * Cleanup
     */
    destroy() {
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        this.analyser = null;
        this.dataArray = null;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AudioAnalyzer };
}
