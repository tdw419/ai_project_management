// sync/event-bus.js
// Simple pub/sub for inter-plugin communication
// Part of CMS Phase 4.1 — Plugin API

import { EventEmitter } from 'events';

/**
 * Well-known event channels that plugins can subscribe to.
 * @type {string[]}
 */
const CANONICAL_EVENTS = [
    'page-change',
    'content-update',
    'theme-change',
    'input',
    'navigation',
];

/**
 * EventBus — lightweight pub/sub for inter-plugin communication.
 *
 * Plugins get a scoped interface via .forPlugin(name) that tracks
 * their subscriptions so the manager can clean up on unload.
 */
export class EventBus extends EventEmitter {
    constructor() {
        super();
        /** @type {Map<string, Map<string, Function[]>>} pluginName -> eventName -> handlers */
        this._pluginSubs = new Map();
        this._maxListeners = 200;
    }

    /**
     * Emit an event. Returns true if any handlers were called.
     * @param {string} event
     * @param {...*} args
     * @returns {boolean}
     */
    emit(event, ...args) {
        return super.emit(event, ...args);
    }

    /**
     * Subscribe to an event.
     * @param {string} event
     * @param {Function} handler
     * @returns {Function} unsubscribe function
     */
    on(event, handler) {
        super.on(event, handler);
        return () => this.off(event, handler);
    }

    /**
     * Subscribe to an event once.
     * @param {string} event
     * @param {Function} handler
     * @returns {Function} unsubscribe function
     */
    once(event, handler) {
        super.once(event, handler);
        return () => this.off(event, handler);
    }

    /**
     * Create a scoped interface for a specific plugin.
     * Tracks subscriptions so they can be cleaned up on unload.
     * @param {string} pluginName
     * @returns {PluginEventBus}
     */
    forPlugin(pluginName) {
        if (!this._pluginSubs.has(pluginName)) {
            this._pluginSubs.set(pluginName, new Map());
        }
        return new PluginEventBus(this, pluginName);
    }

    /**
     * Remove all subscriptions for a plugin.
     * @param {string} pluginName
     * @returns {number} number of handlers removed
     */
    unsubscribeAll(pluginName) {
        const subs = this._pluginSubs.get(pluginName);
        if (!subs) return 0;
        let count = 0;
        for (const [event, handlers] of subs) {
            for (const handler of handlers) {
                super.off(event, handler);
                count++;
            }
        }
        this._pluginSubs.delete(pluginName);
        return count;
    }

    /**
     * Get all active subscriptions for a plugin.
     * @param {string} pluginName
     * @returns {string[]} event names the plugin is subscribed to
     */
    getPluginSubscriptions(pluginName) {
        const subs = this._pluginSubs.get(pluginName);
        return subs ? Array.from(subs.keys()) : [];
    }

    /**
     * Get the list of canonical event names.
     * @returns {string[]}
     */
    static getCanonicalEvents() {
        return [...CANONICAL_EVENTS];
    }

    /**
     * Reset the bus (remove all listeners).
     */
    reset() {
        this.removeAllListeners();
        this._pluginSubs.clear();
    }
}

/**
 * Scoped event bus for a single plugin.
 * Wraps EventBus and auto-tracks subscriptions.
 */
export class PluginEventBus {
    /**
     * @param {EventBus} bus
     * @param {string} pluginName
     */
    constructor(bus, pluginName) {
        this._bus = bus;
        this._pluginName = pluginName;
    }

    /**
     * Subscribe to an event.
     * @param {string} event
     * @param {Function} handler
     * @returns {Function} unsubscribe function
     */
    on(event, handler) {
        this._track(event, handler);
        this._bus.on(event, handler);
        return () => this.off(event, handler);
    }

    /**
     * Subscribe once.
     * @param {string} event
     * @param {Function} handler
     * @returns {Function} unsubscribe function
     */
    once(event, handler) {
        // Wrap handler to auto-untrack on first call
        const wrapped = (...args) => {
            this._untrack(event, handler);
            handler(...args);
        };
        this._track(event, wrapped);
        this._bus.once(event, wrapped);
        return () => this.off(event, wrapped);
    }

    /**
     * Unsubscribe from an event.
     * @param {string} event
     * @param {Function} handler
     */
    off(event, handler) {
        this._untrack(event, handler);
        this._bus.off(event, handler);
    }

    /**
     * Emit an event through the shared bus.
     * @param {string} event
     * @param {...*} args
     * @returns {boolean}
     */
    emit(event, ...args) {
        return this._bus.emit(event, ...args);
    }

    // ── Internal ──────────────────────────────────────────────

    /** @param {string} event @param {Function} handler */
    _track(event, handler) {
        const subs = this._bus._pluginSubs.get(this._pluginName);
        if (!subs) return;
        if (!subs.has(event)) subs.set(event, []);
        subs.get(event).push(handler);
    }

    /** @param {string} event @param {Function} handler */
    _untrack(event, handler) {
        const subs = this._bus._pluginSubs.get(this._pluginName);
        if (!subs) return;
        const handlers = subs.get(event);
        if (!handlers) return;
        const idx = handlers.indexOf(handler);
        if (idx !== -1) handlers.splice(idx, 1);
        if (handlers.length === 0) subs.delete(event);
    }
}
