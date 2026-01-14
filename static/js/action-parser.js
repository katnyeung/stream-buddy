/**
 * ActionParser - Extracts action tags from LLM output text
 *
 * Tag format: [type:name] or [type:name,param:value,param2:value2]
 * Types: mood, gesture, action, eye, head, body
 *
 * Example:
 *   Input:  "[mood:happy] Hello there! [head:nod] How are you? [eye:wink]"
 *   Output: {
 *     cleanText: "Hello there! How are you?",
 *     actions: [
 *       { type: 'mood', name: 'happy', params: {}, position: 0 },
 *       { type: 'head', name: 'nod', params: {}, position: 14 },
 *       { type: 'eye', name: 'wink', params: {}, position: 28 }
 *     ]
 *   }
 */

class ActionParser {
    constructor() {
        // Match [type:name] or [type:name,key:value,key2:value2]
        // Examples: [mood:happy], [gesture:nod,duration:1.2], [action:greet,intensity:0.8]
        this.tagRegex = /\[(\w+):(\w+)(?:,([^\]]+))?\]/g;
    }

    /**
     * Parse text and extract action tags
     * @param {string} text - Raw text with embedded tags
     * @returns {{ cleanText: string, actions: Array<{type: string, name: string, params: object, position: number}> }}
     */
    parse(text) {
        if (!text || typeof text !== 'string') {
            return { cleanText: text || '', actions: [] };
        }

        const actions = [];
        let cleanText = text;
        let match;
        let offset = 0;

        // Reset regex state
        this.tagRegex.lastIndex = 0;

        while ((match = this.tagRegex.exec(text)) !== null) {
            const [fullMatch, type, name, paramsStr] = match;
            const originalPosition = match.index;

            // Parse optional parameters (key:value,key2:value2)
            const params = this._parseParams(paramsStr);

            actions.push({
                type: type.toLowerCase(),
                name: name.toLowerCase(),
                params,
                position: originalPosition - offset  // Position in clean text
            });

            // Track offset for position calculation
            offset += fullMatch.length;
        }

        // Remove all tags from text
        cleanText = text.replace(this.tagRegex, '').trim();
        // Clean up extra spaces
        cleanText = cleanText.replace(/\s+/g, ' ').trim();

        return { cleanText, actions };
    }

    /**
     * Parse comma-separated key:value pairs
     * @param {string} paramsStr - e.g., "intensity:0.8,duration:1.2"
     * @returns {object}
     */
    _parseParams(paramsStr) {
        if (!paramsStr) return {};

        const params = {};
        const pairs = paramsStr.split(',');

        for (const pair of pairs) {
            const [key, value] = pair.split(':').map(s => s.trim());
            if (key && value !== undefined) {
                // Try to parse as number, otherwise keep as string
                const numValue = parseFloat(value);
                params[key.toLowerCase()] = isNaN(numValue) ? value : numValue;
            }
        }

        return params;
    }

    /**
     * Quick check if text contains any action tags
     * @param {string} text
     * @returns {boolean}
     */
    hasActions(text) {
        if (!text) return false;
        this.tagRegex.lastIndex = 0;
        return this.tagRegex.test(text);
    }

    /**
     * Strip all action tags from text (simple version of parse)
     * @param {string} text
     * @returns {string}
     */
    stripTags(text) {
        if (!text) return '';
        return text.replace(this.tagRegex, '').replace(/\s+/g, ' ').trim();
    }

    /**
     * Parse text and estimate timing based on character count before each tag
     * @param {string} text - Raw text with embedded tags
     * @param {number} msPerChar - Milliseconds per character (default 60ms ~150 wpm)
     * @returns {{ cleanText: string, actions: Array<{type: string, name: string, params: object, position: number, delay: number}> }}
     */
    parseWithTiming(text, msPerChar = 60) {
        if (!text || typeof text !== 'string') {
            return { cleanText: text || '', actions: [] };
        }

        const actions = [];
        let cleanText = '';
        let lastIndex = 0;
        let charCount = 0;
        let match;

        // Reset regex state
        this.tagRegex.lastIndex = 0;

        while ((match = this.tagRegex.exec(text)) !== null) {
            const [fullMatch, type, name, paramsStr] = match;

            // Count clean text characters before this tag
            const textBefore = text.slice(lastIndex, match.index);
            const cleanBefore = textBefore.replace(/\s+/g, ' ');
            charCount += cleanBefore.length;
            cleanText += cleanBefore;

            // Parse optional parameters
            const params = this._parseParams(paramsStr);

            // Delay based on characters read so far
            actions.push({
                type: type.toLowerCase(),
                name: name.toLowerCase(),
                params,
                position: match.index,
                delay: Math.floor(charCount * msPerChar)
            });

            lastIndex = match.index + fullMatch.length;
        }

        // Add remaining text
        cleanText += text.slice(lastIndex);
        cleanText = cleanText.replace(/\s+/g, ' ').trim();

        return { cleanText, actions };
    }

    /**
     * Schedule actions to execute at their delay times
     * @param {Array} actions - Actions with delay from parseWithTiming
     * @param {function} executeAction - Callback to execute action: (type, name, params) => void
     * @returns {Array<number>} - Array of timeout IDs (for cancellation)
     */
    scheduleActions(actions, executeAction) {
        const timeouts = [];

        for (const action of actions) {
            const delay = action.delay || 0;
            const timeoutId = setTimeout(() => {
                executeAction(action.type, action.name, action.params);
            }, delay);
            timeouts.push(timeoutId);
        }

        return timeouts;
    }

    /**
     * Cancel scheduled actions
     * @param {Array<number>} timeouts - Timeout IDs from scheduleActions
     */
    cancelScheduled(timeouts) {
        if (timeouts) {
            timeouts.forEach(id => clearTimeout(id));
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ActionParser };
}
