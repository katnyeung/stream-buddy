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

        // Poll every 5 seconds (reduce log spam)
        this.pollInterval = setInterval(() => this.fetchOutline(), 5000);
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
            const points = section.key_points || [];
            const pointsHtml = points.length > 0
                ? `<div class="section-points">${points.map(p => `<span>• ${this.escapeHtml(p)}</span>`).join('')}</div>`
                : '';

            return `
                <li class="section-item upcoming" data-index="${index}">
                    <div class="section-header">
                        <span class="section-number">${index + 1}</span>
                        <span class="section-title">${this.escapeHtml(section.title)}</span>
                    </div>
                    ${pointsHtml}
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
