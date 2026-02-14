/**
 * Outline Page - Pop-out script outline viewer
 * Reads state from Redis via API (source of truth)
 * Polls for updates to stay in sync with main page
 */

class OutlineViewer {
    constructor() {
        this.sectionsList = document.getElementById('sections-list');
        this.progressFill = document.getElementById('progress-fill');
        this.sectionInfo = document.getElementById('section-info');
        this.progressPercent = document.getElementById('progress-percent');
        this.statusDot = document.getElementById('status-dot');
        this.statusText = document.getElementById('status-text');

        this.sessionId = null;
        this.sections = [];
        this.completedSections = new Set();
        this.pollInterval = null;
        this.matchProgress = {};  // {sectionId: {ratio, matched, unmatched, keywords}}
        this.predictions = {};  // {sectionId: [{keyword, cached, hit_count}]}

        this.init();
    }

    init() {
        // Get session_id from localStorage (shared across windows, set by main page)
        this.sessionId = localStorage.getItem('streambuddy_session_id');

        if (!this.sessionId) {
            this.setStatus('waiting', 'No session - open main page first');
            // Keep checking for session_id
            this.pollInterval = setInterval(() => {
                this.sessionId = localStorage.getItem('streambuddy_session_id');
                if (this.sessionId) {
                    console.log('[Outline] Found session:', this.sessionId);
                    this.startPolling();
                }
            }, 1000);
            return;
        }

        console.log('[Outline] Session:', this.sessionId);
        this.startPolling();
    }

    startPolling() {
        // Clear any existing interval
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }

        // Fetch immediately
        this.fetchOutline();

        // Poll every 2 seconds for keyword progress updates
        this.pollInterval = setInterval(() => this.fetchOutline(), 2000);
    }

    async fetchOutline() {
        // Check if session changed (user started new session on main page)
        const currentSessionId = localStorage.getItem('streambuddy_session_id');
        if (currentSessionId && currentSessionId !== this.sessionId) {
            console.log('[Outline] Session changed:', this.sessionId, '->', currentSessionId);
            this.sessionId = currentSessionId;
            // Reset state for new session
            this.sections = [];
            this.completedSections = new Set();
            this.sectionsList.innerHTML = '<li class="section-item loading">Loading new session...</li>';
        }

        if (!this.sessionId) return;

        try {
            const response = await fetch(`/api/session/${this.sessionId}/outline`);
            const data = await response.json();

            if (!data.found) {
                this.setStatus('waiting', 'Waiting for script...');
                return;
            }

            this.setStatus('connected', `Session: ${this.sessionId.slice(0, 8)}`);

            // Redis is source of truth - just render what it returns
            const structure = data.structure;
            if (structure?.sections && structure.sections.length > 0) {
                this.sections = structure.sections;
                this.renderSections();
            }

            // Update progress from Redis
            if (Array.isArray(data.sections_covered)) {
                this.completedSections = new Set(data.sections_covered);
                this.updateVisualState();
            }

            // Update keyword match progress
            if (data.keyword_progress) {
                this.matchProgress = data.keyword_progress;
                this.updateKeywordHighlights();
            }

            // Update prediction cache status
            if (data.predictions) {
                this.predictions = data.predictions;
                this.updatePredictionHighlights();
            }

        } catch (error) {
            console.warn('[Outline] Fetch error:', error);
            this.setStatus('error', 'Connection error');
        }
    }

    setStatus(state, text) {
        this.statusDot.className = 'status-dot ' + state;
        this.statusText.textContent = text;
    }

    renderSections() {
        if (!this.sections.length) {
            this.sectionsList.innerHTML = '<li class="section-item loading">No sections loaded</li>';
            return;
        }

        this.sectionsList.innerHTML = this.sections.map((section, index) => {
            const sectionId = section.id || (index + 1);

            // Filter out action-type key_points (only show speech type)
            const points = (section.key_points || []).filter(p => {
                if (typeof p === 'object') {
                    return p.type !== 'action';
                }
                return true;
            });

            // Get point text
            const pointsHtml = points.length > 0
                ? `<div class="section-points">${points.map(p => {
                    const text = typeof p === 'object' ? p.text : p;
                    return `<span>• ${this.escapeHtml(text)}</span>`;
                }).join('')}</div>`
                : '';

            // Show section keywords with match highlighting
            // Handle both array and string (in case LLM returns wrong format)
            let keywords = section.section_keywords || [];
            if (typeof keywords === 'string') {
                keywords = keywords.split(/[,\s]+/).filter(k => k.length > 0);
            }
            // Split concatenated keywords like "helloEveryoneToday" on camelCase
            keywords = keywords.flatMap(kw => {
                if (kw.length > 15) {
                    // Split on camelCase boundaries
                    return kw.split(/(?<=[a-z])(?=[A-Z])/).filter(k => k.length >= 2);
                }
                return [kw];
            });
            const keywordsHtml = keywords.length > 0
                ? `<div class="section-keywords" data-section-id="${sectionId}">
                    <span class="keywords-label">Keywords:</span>
                    ${keywords.map(k => `<span class="keyword" data-keyword="${this.escapeHtml(k)}">${this.escapeHtml(k)}</span>`).join('')}
                   </div>`
                : '';

            // Keyword match progress bar
            const progressHtml = `<div class="keyword-progress-bar" data-section-id="${sectionId}">
                <div class="keyword-progress-fill" style="width: 0%"></div>
                <span class="keyword-progress-text">0%</span>
            </div>`;

            // Predicted keywords (if prediction cache enabled)
            const sectionPredictions = this.predictions[sectionId] || [];
            const predictionsHtml = sectionPredictions.length > 0
                ? `<div class="section-predictions" data-section-id="${sectionId}">
                    <span class="predictions-label">Cached:</span>
                    ${sectionPredictions.map(p => `<span class="prediction-keyword${p.cached ? ' cached' : ''}" data-keyword="${this.escapeHtml(p.keyword)}">${this.escapeHtml(p.keyword)}</span>`).join('')}
                   </div>`
                : '';

            return `
                <li class="section-item upcoming" data-index="${index}" data-section-id="${sectionId}">
                    <div class="section-header">
                        <span class="section-number">${index + 1}</span>
                        <span class="section-title">${this.escapeHtml(section.title)}</span>
                    </div>
                    ${pointsHtml}
                    ${keywordsHtml}
                    ${progressHtml}
                    ${predictionsHtml}
                </li>
            `;
        }).join('');

        // Mark first section as current
        const firstItem = this.sectionsList.querySelector('[data-index="0"]');
        if (firstItem) {
            firstItem.classList.remove('upcoming');
            firstItem.classList.add('current');
        }

        this.updateProgressBar();
        this.updateKeywordHighlights();
    }

    updatePredictionHighlights() {
        // Update prediction keyword highlights
        for (const [sectionId, predictions] of Object.entries(this.predictions)) {
            const container = this.sectionsList.querySelector(`.section-predictions[data-section-id="${sectionId}"]`);
            if (!container) continue;

            container.querySelectorAll('.prediction-keyword').forEach(el => {
                const keyword = el.dataset.keyword.toLowerCase();
                const pred = predictions.find(p => p.keyword.toLowerCase() === keyword);
                if (pred?.cached) el.classList.add('cached');
                if (pred?.hit) {
                    el.classList.add('hit');
                    // Remove hit class after animation
                    setTimeout(() => el.classList.remove('hit'), 500);
                }
            });
        }
    }

    updateKeywordHighlights() {
        // Update keyword highlights based on matchProgress
        for (const [sectionId, progress] of Object.entries(this.matchProgress)) {
            const container = this.sectionsList.querySelector(`.section-keywords[data-section-id="${sectionId}"]`);
            if (!container) continue;

            // Highlight matched keywords
            const matched = new Set((progress.matched || []).map(k => k.toLowerCase()));
            container.querySelectorAll('.keyword').forEach(keywordEl => {
                const keyword = keywordEl.dataset.keyword.toLowerCase();
                if (matched.has(keyword)) {
                    keywordEl.classList.add('matched');
                } else {
                    keywordEl.classList.remove('matched');
                }
            });

            // Update progress bar
            const progressBar = this.sectionsList.querySelector(`.keyword-progress-bar[data-section-id="${sectionId}"]`);
            if (progressBar) {
                const ratio = progress.ratio || 0;
                const fill = progressBar.querySelector('.keyword-progress-fill');
                const text = progressBar.querySelector('.keyword-progress-text');
                if (fill) fill.style.width = `${ratio}%`;
                if (text) text.textContent = `${ratio}%`;

                // Color based on progress
                if (progress.complete) {
                    progressBar.classList.add('complete');
                } else if (ratio >= 50) {
                    progressBar.classList.add('good');
                    progressBar.classList.remove('complete');
                } else {
                    progressBar.classList.remove('good', 'complete');
                }
            }
        }
    }

    updateVisualState() {
        // Update visual state based on completedSections from Redis
        const items = this.sectionsList.querySelectorAll('.section-item[data-index]');
        let foundCurrent = false;

        items.forEach(item => {
            const idx = parseInt(item.dataset.index);
            // Redis uses 1-based section IDs
            if (this.completedSections.has(idx + 1)) {
                item.classList.remove('current', 'upcoming');
                item.classList.add('completed');
            } else if (!foundCurrent) {
                item.classList.remove('upcoming', 'completed');
                item.classList.add('current');
                foundCurrent = true;
            } else {
                item.classList.remove('current', 'completed');
                item.classList.add('upcoming');
            }
        });

        this.updateProgressBar();
    }

    updateProgressBar() {
        const progress = this.sections.length > 0
            ? (this.completedSections.size / this.sections.length) * 100
            : 0;
        this.progressFill.style.width = `${progress}%`;
        this.progressPercent.textContent = `${Math.round(progress)}%`;

        const currentSection = Math.min(this.completedSections.size + 1, this.sections.length);
        this.sectionInfo.textContent = `Section ${currentSection} of ${this.sections.length}`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    destroy() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.outlineViewer = new OutlineViewer();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.outlineViewer) {
        window.outlineViewer.destroy();
    }
});
