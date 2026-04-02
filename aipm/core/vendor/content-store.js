// sync/content-store.js
// CMS content store — pages, posts, and media references
// Backed by a JSON file (data/content.json)

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { dirname } from 'path';

/**
 * @typedef {Object} ContentItem
 * @property {string} id       - Unique identifier (UUID-style)
 * @property {'page'|'post'|'media'} type - Content type
 * @property {string} title    - Display title
 * @property {string} body     - Main content body (markdown or plain text)
 * @property {Object} metadata - Arbitrary key-value metadata (tags, author, etc.)
 * @property {number} created_at - Unix timestamp (ms)
 * @property {number} updated_at - Unix timestamp (ms)
 */

/**
 * @typedef {Object} LayoutRegion
 * @property {string} region     - Region name: header, body, sidebar, footer
 * @property {string|null} contentId - Bound content item ID, or null for inline
 * @property {string|null} inline    - Inline content when contentId is null
 * @property {string|null} formula   - Optional formula for dynamic positioning
 */

/**
 * @typedef {Object} PageManifest
 * @property {string} id          - Unique identifier
 * @property {string} title       - Page title
 * @property {string} slug        - URL-safe slug
 * @property {LayoutRegion[]} layout - Ordered list of layout regions
 * @property {string|null} theme  - Theme reference name
 * @property {Object} metadata    - Arbitrary page-level metadata
 * @property {number} created_at  - Unix timestamp (ms)
 * @property {number} updated_at  - Unix timestamp (ms)
 */

const VALID_TYPES = new Set(['page', 'post', 'media']);
const VALID_REGIONS = new Set(['header', 'body', 'sidebar', 'footer']);

let _idCounter = 0;

function generateId() {
    return `c_${Date.now().toString(36)}_${(++_idCounter).toString(36)}`;
}

function generateManifestId() {
    return `pm_${Date.now().toString(36)}_${(++_idCounter).toString(36)}`;
}

export class ContentStore {
    /**
     * @param {Object} [options]
     * @param {string} [options.filePath] - Path to JSON file for persistence
     * @param {number} [options.saveDelay] - Debounce delay in ms (default 1000)
     */
    constructor(options = {}) {
        /** @type {Map<string, ContentItem>} */
        this.items = new Map();
        /** @type {Map<string, PageManifest>} */
        this.manifests = new Map();
        this.filePath = options.filePath;
        this.saveDelay = options.saveDelay || 1000;
        this._saveTimeout = null;

        if (this.filePath) {
            this._loadFromFile();
        }
    }

    // ── Content CRUD ───────────────────────────────────────────

    /**
     * Create a new content item.
     * @param {Object} input
     * @param {'page'|'post'|'media'} input.type
     * @param {string} input.title
     * @param {string} [input.body='']
     * @param {Object} [input.metadata={}]
     * @returns {ContentItem}
     */
    create({ type, title, body = '', metadata = {} }) {
        if (!VALID_TYPES.has(type)) {
            throw new Error(`Invalid content type: ${type}`);
        }
        if (!title || typeof title !== 'string') {
            throw new Error('Title is required');
        }
        const now = Date.now();
        const item = {
            id: generateId(),
            type,
            title,
            body,
            metadata: { ...metadata },
            created_at: now,
            updated_at: now,
        };
        this.items.set(item.id, item);
        this._scheduleSave();
        return item;
    }

    /**
     * Read a content item by ID.
     * @param {string} id
     * @returns {ContentItem|null}
     */
    read(id) {
        const item = this.items.get(id);
        return item ? { ...item, metadata: { ...item.metadata } } : null;
    }

    /**
     * Update a content item.
     * @param {string} id
     * @param {Object} updates
     * @returns {ContentItem|null}
     */
    update(id, updates) {
        const item = this.items.get(id);
        if (!item) return null;
        if (updates.type !== undefined && !VALID_TYPES.has(updates.type)) {
            throw new Error(`Invalid content type: ${updates.type}`);
        }
        const allowed = ['type', 'title', 'body', 'metadata'];
        for (const key of allowed) {
            if (updates[key] !== undefined) {
                item[key] = key === 'metadata' ? { ...updates[key] } : updates[key];
            }
        }
        item.updated_at = Date.now();
        this._scheduleSave();
        return { ...item, metadata: { ...item.metadata } };
    }

    /**
     * Delete a content item.
     * @param {string} id
     * @returns {boolean}
     */
    delete(id) {
        const existed = this.items.delete(id);
        if (existed) this._scheduleSave();
        return existed;
    }

    /**
     * List content items with optional filtering.
     * @param {Object} [filter]
     * @param {'page'|'post'|'media'} [filter.type] - Filter by type
     * @param {string} [filter.tag] - Filter by metadata tag
     * @returns {ContentItem[]}
     */
    list(filter = {}) {
        let results = Array.from(this.items.values());
        if (filter.type) {
            results = results.filter(item => item.type === filter.type);
        }
        if (filter.tag) {
            results = results.filter(item => {
                const tags = item.metadata.tags;
                return Array.isArray(tags) && tags.includes(filter.tag);
            });
        }
        return results.map(item => ({ ...item, metadata: { ...item.metadata } }));
    }

    /**
     * Full-text search over title + body.
     * @param {string} query - Search string (case-insensitive)
     * @returns {ContentItem[]}
     */
    search(query) {
        if (!query || typeof query !== 'string') return [];
        const lower = query.toLowerCase();
        return Array.from(this.items.values())
            .filter(item =>
                item.title.toLowerCase().includes(lower) ||
                item.body.toLowerCase().includes(lower)
            )
            .map(item => ({ ...item, metadata: { ...item.metadata } }));
    }

    // ── Page Manifest CRUD ─────────────────────────────────────

    /**
     * Create a page manifest.
     * @param {Object} input
     * @param {string} input.title
     * @param {string} [input.slug] - Auto-generated from title if omitted
     * @param {LayoutRegion[]} [input.layout=[]]
     * @param {string|null} [input.theme=null]
     * @param {Object} [input.metadata={}]
     * @returns {PageManifest}
     */
    createManifest({ title, slug, layout = [], theme = null, metadata = {} }) {
        if (!title || typeof title !== 'string') {
            throw new Error('Title is required');
        }
        this._validateLayout(layout);
        const now = Date.now();
        const manifest = {
            id: generateManifestId(),
            title,
            slug: slug || this._slugify(title),
            layout: layout.map(r => ({ ...r })),
            theme,
            metadata: { ...metadata },
            created_at: now,
            updated_at: now,
        };
        this.manifests.set(manifest.id, manifest);
        this._scheduleSave();
        return { ...manifest, layout: manifest.layout.map(r => ({ ...r })), metadata: { ...manifest.metadata } };
    }

    /**
     * Read a page manifest by ID.
     * @param {string} id
     * @returns {PageManifest|null}
     */
    readManifest(id) {
        const m = this.manifests.get(id);
        if (!m) return null;
        return { ...m, layout: m.layout.map(r => ({ ...r })), metadata: { ...m.metadata } };
    }

    /**
     * Update a page manifest.
     * @param {string} id
     * @param {Object} updates
     * @returns {PageManifest|null}
     */
    updateManifest(id, updates) {
        const m = this.manifests.get(id);
        if (!m) return null;
        if (updates.layout) this._validateLayout(updates.layout);
        const allowed = ['title', 'slug', 'layout', 'theme', 'metadata'];
        for (const key of allowed) {
            if (updates[key] !== undefined) {
                if (key === 'layout') {
                    m.layout = updates.layout.map(r => ({ ...r }));
                } else if (key === 'metadata') {
                    m.metadata = { ...updates.metadata };
                } else {
                    m[key] = updates[key];
                }
            }
        }
        m.updated_at = Date.now();
        this._scheduleSave();
        return { ...m, layout: m.layout.map(r => ({ ...r })), metadata: { ...m.metadata } };
    }

    /**
     * Delete a page manifest.
     * @param {string} id
     * @returns {boolean}
     */
    deleteManifest(id) {
        const existed = this.manifests.delete(id);
        if (existed) this._scheduleSave();
        return existed;
    }

    /**
     * List all page manifests.
     * @returns {PageManifest[]}
     */
    listManifests() {
        return Array.from(this.manifests.values()).map(m => ({
            ...m,
            layout: m.layout.map(r => ({ ...r })),
            metadata: { ...m.metadata },
        }));
    }

    // ── Validation ─────────────────────────────────────────────

    /**
     * Validate layout regions.
     * @param {LayoutRegion[]} layout
     */
    _validateLayout(layout) {
        if (!Array.isArray(layout)) {
            throw new Error('Layout must be an array');
        }
        for (const region of layout) {
            if (!VALID_REGIONS.has(region.region)) {
                throw new Error(`Invalid region: ${region.region}`);
            }
            if (region.contentId !== null && region.contentId !== undefined) {
                if (typeof region.contentId !== 'string') {
                    throw new Error('contentId must be a string or null');
                }
            }
        }
    }

    // ── Persistence ────────────────────────────────────────────

    _scheduleSave() {
        if (!this.filePath) return;
        if (this._saveTimeout) clearTimeout(this._saveTimeout);
        this._saveTimeout = setTimeout(() => this._saveToFile(), this.saveDelay);
    }

    _saveToFile() {
        if (!this.filePath) return false;
        try {
            const data = {
                version: 1,
                items: Object.fromEntries(this.items),
                manifests: Object.fromEntries(this.manifests),
            };
            const dir = dirname(this.filePath);
            if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
            writeFileSync(this.filePath, JSON.stringify(data, null, 2));
            return true;
        } catch (err) {
            console.error('Failed to save content store:', err.message);
            return false;
        }
    }

    _loadFromFile() {
        if (!this.filePath || !existsSync(this.filePath)) return false;
        try {
            const raw = readFileSync(this.filePath, 'utf-8');
            const data = JSON.parse(raw);
            if (data.version !== 1) return false;
            if (data.items) {
                this.items = new Map(Object.entries(data.items));
            }
            if (data.manifests) {
                this.manifests = new Map(Object.entries(data.manifests));
            }
            return true;
        } catch (err) {
            console.error('Failed to load content store:', err.message);
            return false;
        }
    }

    /**
     * Force-save to disk (bypass debounce).
     * @returns {boolean}
     */
    saveNow() {
        if (this._saveTimeout) {
            clearTimeout(this._saveTimeout);
            this._saveTimeout = null;
        }
        return this._saveToFile();
    }

    // ── Helpers ────────────────────────────────────────────────

    _slugify(text) {
        return text
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '');
    }
}
