/**
 * Overlay Manager - Foundation for VTuber screen overlays
 *
 * Manages PIXI containers for overlay elements that appear
 * above the avatar on the OBS canvas.
 *
 * Layer structure:
 *   - background: Background effects, environment
 *   - avatar: Live2D model (managed by OBSAvatar)
 *   - overlays: Text boxes, images, UI elements
 *   - ui: Debug info, always on top
 *
 * Future overlay types:
 *   - Text boxes (speech bubbles, captions)
 *   - Image overlays (product images, screenshots)
 *   - Annotations (arrows, highlights)
 *   - Particle effects
 */

class OverlayManager {
    /**
     * @param {PIXI.Container} overlayContainer - The PIXI container for overlays
     * @param {number} canvasWidth - Canvas width (default 1920)
     * @param {number} canvasHeight - Canvas height (default 1080)
     */
    constructor(overlayContainer, canvasWidth = 1920, canvasHeight = 1080) {
        this.container = overlayContainer;
        this.width = canvasWidth;
        this.height = canvasHeight;

        // Active overlays by ID
        this.overlays = new Map();

        // Overlay type handlers
        this.handlers = {
            text: this._createTextOverlay.bind(this),
            image: this._createImageOverlay.bind(this),
            box: this._createBoxOverlay.bind(this)
        };

        // Animation state
        this.animations = new Map();
    }

    /**
     * Create and show an overlay
     * @param {string} id - Unique identifier for the overlay
     * @param {string} type - Overlay type ('text', 'image', 'box')
     * @param {object} options - Type-specific options
     * @returns {PIXI.DisplayObject} The created overlay object
     */
    show(id, type, options = {}) {
        // Remove existing overlay with same ID
        if (this.overlays.has(id)) {
            this.hide(id);
        }

        // Create overlay using type handler
        const handler = this.handlers[type];
        if (!handler) {
            console.warn(`[OverlayManager] Unknown overlay type: ${type}`);
            return null;
        }

        const overlay = handler(options);
        if (!overlay) return null;

        // Position overlay
        this._positionOverlay(overlay, options);

        // Add to container and track
        this.container.addChild(overlay);
        this.overlays.set(id, { object: overlay, type, options });

        // Animate in if specified
        if (options.animateIn) {
            this._animateIn(id, options.animateIn);
        }

        console.log(`[OverlayManager] Showing overlay: ${id} (${type})`);
        return overlay;
    }

    /**
     * Hide and remove an overlay
     * @param {string} id - Overlay ID to hide
     * @param {string} animateOut - Animation type for removal (optional)
     */
    hide(id, animateOut = null) {
        const overlayData = this.overlays.get(id);
        if (!overlayData) return;

        if (animateOut) {
            this._animateOut(id, animateOut, () => {
                this._removeOverlay(id);
            });
        } else {
            this._removeOverlay(id);
        }
    }

    /**
     * Remove overlay immediately
     * @private
     */
    _removeOverlay(id) {
        const overlayData = this.overlays.get(id);
        if (!overlayData) return;

        this.container.removeChild(overlayData.object);
        overlayData.object.destroy({ children: true });
        this.overlays.delete(id);

        // Cancel any running animation
        if (this.animations.has(id)) {
            cancelAnimationFrame(this.animations.get(id));
            this.animations.delete(id);
        }

        console.log(`[OverlayManager] Hidden overlay: ${id}`);
    }

    /**
     * Hide all overlays
     */
    hideAll() {
        for (const id of this.overlays.keys()) {
            this.hide(id);
        }
    }

    /**
     * Update overlay content
     * @param {string} id - Overlay ID
     * @param {object} updates - Properties to update
     */
    update(id, updates) {
        const overlayData = this.overlays.get(id);
        if (!overlayData) return;

        const overlay = overlayData.object;

        // Update position
        if (updates.x !== undefined) overlay.x = updates.x;
        if (updates.y !== undefined) overlay.y = updates.y;
        if (updates.alpha !== undefined) overlay.alpha = updates.alpha;
        if (updates.scale !== undefined) {
            overlay.scale.set(updates.scale, updates.scale);
        }

        // Type-specific updates
        if (overlayData.type === 'text' && updates.text !== undefined) {
            overlay.text = updates.text;
        }
    }

    // === Overlay Type Handlers ===

    /**
     * Create text overlay
     * @private
     */
    _createTextOverlay(options) {
        const style = new PIXI.TextStyle({
            fontFamily: options.fontFamily || 'Arial, sans-serif',
            fontSize: options.fontSize || 48,
            fill: options.color || 0xFFFFFF,
            stroke: options.strokeColor || 0x000000,
            strokeThickness: options.strokeThickness || 4,
            wordWrap: options.wordWrap !== false,
            wordWrapWidth: options.maxWidth || 800,
            align: options.align || 'center',
            dropShadow: options.shadow !== false,
            dropShadowColor: 0x000000,
            dropShadowBlur: 4,
            dropShadowDistance: 2
        });

        const text = new PIXI.Text(options.text || '', style);
        text.anchor.set(0.5, 0.5);

        return text;
    }

    /**
     * Create image overlay
     * @private
     */
    _createImageOverlay(options) {
        // Create placeholder - actual image loading would be async
        const container = new PIXI.Container();

        if (options.url) {
            // Load image asynchronously
            const sprite = PIXI.Sprite.from(options.url);
            sprite.anchor.set(0.5, 0.5);

            if (options.maxWidth || options.maxHeight) {
                sprite.texture.on('update', () => {
                    this._constrainSize(sprite, options.maxWidth, options.maxHeight);
                });
            }

            container.addChild(sprite);
        }

        return container;
    }

    /**
     * Create box overlay (rounded rectangle container)
     * @private
     */
    _createBoxOverlay(options) {
        const container = new PIXI.Container();

        // Background
        const bg = new PIXI.Graphics();
        const width = options.width || 400;
        const height = options.height || 200;
        const radius = options.radius || 16;
        const bgColor = options.bgColor || 0x1a1a2e;
        const bgAlpha = options.bgAlpha ?? 0.9;

        bg.beginFill(bgColor, bgAlpha);
        bg.drawRoundedRect(-width/2, -height/2, width, height, radius);
        bg.endFill();

        // Border
        if (options.borderColor) {
            bg.lineStyle(options.borderWidth || 2, options.borderColor, 1);
            bg.drawRoundedRect(-width/2, -height/2, width, height, radius);
        }

        container.addChild(bg);

        // Add text if provided
        if (options.text) {
            const textStyle = new PIXI.TextStyle({
                fontFamily: options.fontFamily || 'Arial, sans-serif',
                fontSize: options.fontSize || 24,
                fill: options.textColor || 0xFFFFFF,
                wordWrap: true,
                wordWrapWidth: width - 40,
                align: options.textAlign || 'center'
            });

            const text = new PIXI.Text(options.text, textStyle);
            text.anchor.set(0.5, 0.5);
            container.addChild(text);
        }

        return container;
    }

    // === Positioning ===

    /**
     * Position overlay based on options
     * @private
     */
    _positionOverlay(overlay, options) {
        // Direct coordinates
        if (options.x !== undefined) overlay.x = options.x;
        if (options.y !== undefined) overlay.y = options.y;

        // Named positions
        if (options.position) {
            const positions = this._getNamedPositions();
            const pos = positions[options.position];
            if (pos) {
                overlay.x = pos.x;
                overlay.y = pos.y;
            }
        }

        // Offset from avatar zone
        if (options.zone && options.offsetX !== undefined) {
            const zones = { left: 400, center: 960, right: 1520 };
            overlay.x = (zones[options.zone] || 960) + (options.offsetX || 0);
        }

        // Alpha
        if (options.alpha !== undefined) {
            overlay.alpha = options.alpha;
        }

        // Scale
        if (options.scale !== undefined) {
            overlay.scale.set(options.scale, options.scale);
        }
    }

    /**
     * Get named position presets
     * @private
     */
    _getNamedPositions() {
        return {
            // Corners
            topLeft: { x: 100, y: 100 },
            topRight: { x: this.width - 100, y: 100 },
            bottomLeft: { x: 100, y: this.height - 100 },
            bottomRight: { x: this.width - 100, y: this.height - 100 },

            // Center positions
            center: { x: this.width / 2, y: this.height / 2 },
            topCenter: { x: this.width / 2, y: 150 },
            bottomCenter: { x: this.width / 2, y: this.height - 150 },

            // Thirds
            leftThird: { x: this.width / 3, y: this.height / 2 },
            rightThird: { x: (this.width * 2) / 3, y: this.height / 2 },

            // Above avatar (when avatar is at bottom)
            aboveAvatar: { x: this.width / 2, y: this.height * 0.4 }
        };
    }

    // === Animations ===

    /**
     * Animate overlay in
     * @private
     */
    _animateIn(id, animation) {
        const overlayData = this.overlays.get(id);
        if (!overlayData) return;

        const overlay = overlayData.object;
        const startTime = performance.now();
        const duration = 300;

        switch (animation) {
            case 'fade':
                overlay.alpha = 0;
                this._runAnimation(id, startTime, duration, (progress) => {
                    overlay.alpha = progress;
                });
                break;

            case 'scale':
                overlay.scale.set(0, 0);
                overlay.alpha = 0;
                this._runAnimation(id, startTime, duration, (progress) => {
                    const eased = 1 - Math.pow(1 - progress, 3);
                    overlay.scale.set(eased, eased);
                    overlay.alpha = eased;
                });
                break;

            case 'slideDown':
                const targetY = overlay.y;
                overlay.y = targetY - 50;
                overlay.alpha = 0;
                this._runAnimation(id, startTime, duration, (progress) => {
                    const eased = 1 - Math.pow(1 - progress, 3);
                    overlay.y = targetY - 50 + 50 * eased;
                    overlay.alpha = eased;
                });
                break;
        }
    }

    /**
     * Animate overlay out
     * @private
     */
    _animateOut(id, animation, onComplete) {
        const overlayData = this.overlays.get(id);
        if (!overlayData) {
            onComplete?.();
            return;
        }

        const overlay = overlayData.object;
        const startTime = performance.now();
        const duration = 200;

        switch (animation) {
            case 'fade':
                this._runAnimation(id, startTime, duration, (progress) => {
                    overlay.alpha = 1 - progress;
                }, onComplete);
                break;

            case 'scale':
                this._runAnimation(id, startTime, duration, (progress) => {
                    const eased = 1 - Math.pow(1 - progress, 3);
                    overlay.scale.set(1 - eased, 1 - eased);
                    overlay.alpha = 1 - eased;
                }, onComplete);
                break;

            default:
                onComplete?.();
        }
    }

    /**
     * Run animation loop
     * @private
     */
    _runAnimation(id, startTime, duration, updateFn, onComplete = null) {
        const animate = () => {
            const elapsed = performance.now() - startTime;
            const progress = Math.min(1, elapsed / duration);

            updateFn(progress);

            if (progress < 1) {
                this.animations.set(id, requestAnimationFrame(animate));
            } else {
                this.animations.delete(id);
                onComplete?.();
            }
        };

        this.animations.set(id, requestAnimationFrame(animate));
    }

    // === Utilities ===

    /**
     * Constrain sprite size to max dimensions
     * @private
     */
    _constrainSize(sprite, maxWidth, maxHeight) {
        const texture = sprite.texture;
        if (!texture.valid) return;

        const aspectRatio = texture.width / texture.height;

        let targetWidth = texture.width;
        let targetHeight = texture.height;

        if (maxWidth && targetWidth > maxWidth) {
            targetWidth = maxWidth;
            targetHeight = targetWidth / aspectRatio;
        }

        if (maxHeight && targetHeight > maxHeight) {
            targetHeight = maxHeight;
            targetWidth = targetHeight * aspectRatio;
        }

        sprite.width = targetWidth;
        sprite.height = targetHeight;
    }

    /**
     * Get overlay count
     */
    get count() {
        return this.overlays.size;
    }

    /**
     * Check if overlay exists
     */
    has(id) {
        return this.overlays.has(id);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { OverlayManager };
}
