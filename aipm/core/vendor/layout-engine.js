// sync/layout-engine.js — Named layout regions with formula-based bounds computation
// Part of ascii-world-core CMS

import { EventEmitter } from 'events';
import { readFileSync, readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PRESETS_DIR = join(__dirname, 'layout-presets');

/**
 * Evaluate a simple formula string in the context of W (width) and H (height).
 * Supported tokens: integers, W, H, +, -, *, /, parentheses, floor()
 * Returns an integer (Math.floor of result).
 */
function evalFormula(expr, W, H) {
    // Replace tokens for safe evaluation
    let sanitized = expr
        .replace(/\bfloor\b/g, 'Math.floor')
        .replace(/\bW\b/g, String(W))
        .replace(/\bH\b/g, String(H));

    // Validate: only allow digits, Math.floor, whitespace, parens, and arithmetic operators
    if (!/^[\d\s+\-*/().Mathfloor]+$/.test(sanitized)) {
        throw new Error(`Invalid formula expression: "${expr}"`);
    }

    // Use Function constructor for safe-ish evaluation (no access to globals)
    try {
        const result = new Function('Math', `"use strict"; return (${sanitized});`)(Math);
        return Math.floor(result);
    } catch (err) {
        throw new Error(`Failed to evaluate formula "${expr}": ${err.message}`);
    }
}

/**
 * Load all preset JSON files from the layout-presets/ directory.
 * Returns a Map of presetName -> presetDefinition.
 */
function loadPresetFiles() {
    const presets = new Map();
    try {
        const files = readdirSync(PRESETS_DIR).filter(f => f.endsWith('.json'));
        for (const file of files) {
            const raw = readFileSync(join(PRESETS_DIR, file), 'utf-8');
            const preset = JSON.parse(raw);
            presets.set(preset.name, preset);
        }
    } catch {
        // Presets directory may not exist in test environments; return empty map
    }
    return presets;
}

// Load built-in presets once at module level
const LAYOUT_PRESETS = loadPresetFiles();

/**
 * LayoutEngine — manages named layout regions with formula-based bounds.
 *
 * Each region has { name, x, y, w, h } where x/y/w/h are formula strings
 * evaluated against the current width (W) and height (H).
 *
 * Usage:
 *   const engine = new LayoutEngine({ width: 80, height: 24 });
 *   engine.loadPreset('two-column');
 *   const body = engine.getRegion('body'); // { name, x, y, w, h } with computed integers
 *   engine.resize(120, 40); // recomputes all regions
 */
export class LayoutEngine extends EventEmitter {
    /**
     * @param {object} options
     * @param {number} options.width  - Grid width in cells (default 80)
     * @param {number} options.height - Grid height in cells (default 24)
     */
    constructor(options = {}) {
        super();
        this.width = options.width || 80;
        this.height = options.height || 24;
        this._currentPresetName = null;
        this._regions = new Map(); // name -> { name, x, y, w, h } (formula strings)
        this._computed = new Map(); // name -> { name, x, y, w, h } (evaluated integers)
    }

    /**
     * Load a named preset. Recomputes region bounds.
     * @param {string} name - Preset name (e.g. 'two-column')
     * @returns {boolean} true if preset found and loaded
     */
    loadPreset(name) {
        const preset = LAYOUT_PRESETS.get(name);
        if (!preset) {
            return false;
        }

        this._currentPresetName = name;
        this._regions.clear();
        this._computed.clear();

        for (const regionDef of preset.regions) {
            this._regions.set(regionDef.name, {
                name: regionDef.name,
                x: regionDef.x,
                y: regionDef.y,
                w: regionDef.w,
                h: regionDef.h
            });
        }

        this._computeAll();
        this.emit('preset-loaded', { name, regions: this.getAllRegions() });
        return true;
    }

    /**
     * Get a computed region by name.
     * @param {string} name
     * @returns {{ name, x, y, w, h }|undefined}
     */
    getRegion(name) {
        return this._computed.get(name);
    }

    /**
     * Get all computed regions as a Map.
     * @returns {Map<string, { name, x, y, w, h }>}
     */
    getAllRegions() {
        return new Map(this._computed);
    }

    /**
     * Get the name of the currently loaded preset.
     * @returns {string|null}
     */
    get currentPreset() {
        return this._currentPresetName;
    }

    /**
     * Resize the layout grid and recompute all region bounds proportionally.
     * @param {number} width
     * @param {number} height
     */
    resize(width, height) {
        const oldWidth = this.width;
        const oldHeight = this.height;
        this.width = width;
        this.height = height;
        this._computeAll();
        this.emit('resized', { width, height, oldWidth, oldHeight, regions: this.getAllRegions() });
    }

    /**
     * Recompute all region bounds from their formulas.
     * @private
     */
    _computeAll() {
        this._computed.clear();
        for (const [name, region] of this._regions) {
            this._computed.set(name, {
                name,
                x: evalFormula(region.x, this.width, this.height),
                y: evalFormula(region.y, this.width, this.height),
                w: evalFormula(region.w, this.width, this.height),
                h: evalFormula(region.h, this.width, this.height)
            });
        }
    }

    /**
     * Check if a cell position falls within a named region.
     * @param {string} name - Region name
     * @param {number} cx - Cell x (column)
     * @param {number} cy - Cell y (row)
     * @returns {boolean}
     */
    isInside(name, cx, cy) {
        const r = this._computed.get(name);
        if (!r) return false;
        return cx >= r.x && cx < r.x + r.w && cy >= r.y && cy < r.y + r.h;
    }

    /**
     * Find which region a cell position belongs to.
     * @param {number} cx - Cell x (column)
     * @param {number} cy - Cell y (row)
     * @returns {string|null} Region name or null
     */
    regionAt(cx, cy) {
        for (const [name, r] of this._computed) {
            if (cx >= r.x && cx < r.x + r.w && cy >= r.y && cy < r.y + r.h) {
                return name;
            }
        }
        return null;
    }
}

export { LAYOUT_PRESETS, evalFormula };
