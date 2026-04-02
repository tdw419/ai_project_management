/**
 * theme-manager.js
 * CMS Theme Manager — loads, applies, creates, and deletes themes.
 * Extends EventEmitter for theme lifecycle events.
 *
 * Built-in themes are sourced from theme-editor.js THEME_PRESETS.
 * Custom themes are stored as JSON files in the themes/ directory.
 */

import { EventEmitter } from 'node:events';
import { readFile, writeFile, unlink, readdir, mkdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { THEME_PRESETS } from './theme-editor.js';

class ThemeManager extends EventEmitter {
  /**
   * @param {object} [options]
   * @param {string} [options.themesDir]  - Directory for theme JSON files (default: themes/)
   * @param {import('./pixel-formula-engine.js').PixelFormulaEngine} [options.pixelFormulaEngine] - Engine to apply palette to
   */
  constructor(options = {}) {
    super();
    this._themesDir = options.themesDir
      ? resolve(options.themesDir)
      : resolve('themes');
    this._engine = options.pixelFormulaEngine || null;
    this._activeTheme = null;
    this._cache = new Map(); // name -> theme object
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Load a theme by name. Checks built-in presets first, then files.
   * @param {string} name
   * @returns {Promise<object>} theme object { name, description, colors }
   */
  async loadTheme(name) {
    if (typeof name !== 'string' || name.length === 0) {
      throw new Error('Theme name must be a non-empty string');
    }

    // 1. Check cache (always return a clone to prevent external mutation)
    if (this._cache.has(name)) {
      return this._cloneTheme(this._cache.get(name));
    }

    // 2. Check built-in presets
    if (THEME_PRESETS[name]) {
      const theme = this._cloneTheme(THEME_PRESETS[name]);
      this._cache.set(name, theme);
      return this._cloneTheme(theme);
    }

    // 3. Try file system
    const theme = await this._loadThemeFile(name);
    this._cache.set(name, theme);
    return this._cloneTheme(theme);
  }

  /**
   * List all available themes (built-in + file-based).
   * @returns {Promise<Array<{name:string, description:string, colors:object}>>}
   */
  async listThemes() {
    const themes = [];

    // Built-in presets
    for (const [name, preset] of Object.entries(THEME_PRESETS)) {
      themes.push({
        name: preset.name,
        description: preset.description,
        colors: { ...preset.colors },
      });
    }

    // File-based themes
    try {
      await mkdir(this._themesDir, { recursive: true });
      const files = await readdir(this._themesDir);
      const jsonFiles = files.filter((f) => f.endsWith('.json'));

      for (const file of jsonFiles) {
        try {
          const theme = await this._loadThemeFile(file.replace('.json', ''));
          // Avoid duplicates if a file shadows a built-in
          const existing = themes.find((t) => t.name === theme.name);
          if (!existing) {
            themes.push(theme);
          }
        } catch {
          // Skip malformed theme files silently
        }
      }
    } catch {
      // themes/ dir may not exist yet; that's fine
    }

    return themes;
  }

  /**
   * Get the currently active theme.
   * @returns {object|null}
   */
  getActiveTheme() {
    return this._activeTheme ? this._cloneTheme(this._activeTheme) : null;
  }

  /**
   * Apply a theme by name. Sets active theme, applies palette to engine, emits event.
   * @param {string} name
   * @returns {Promise<object>} the applied theme
   */
  async applyTheme(name) {
    const theme = await this.loadTheme(name);
    const previous = this._activeTheme;

    this._activeTheme = this._cloneTheme(theme);

    // Apply to pixel formula engine if available
    if (this._engine && typeof this._engine.setPalette === 'function') {
      this._engine.setPalette(theme.colors);
    }

    this.emit('theme-changed', {
      theme: this._cloneTheme(theme),
      previous: previous ? this._cloneTheme(previous) : null,
    });

    return this._cloneTheme(theme);
  }

  /**
   * Create a new theme and persist it as a JSON file.
   * @param {string} name
   * @param {object} colors - Color map
   * @param {string} [description='']
   * @returns {Promise<object>} the created theme
   */
  async createTheme(name, colors, description = '') {
    if (typeof name !== 'string' || name.length === 0) {
      throw new Error('Theme name must be a non-empty string');
    }
    if (!colors || typeof colors !== 'object') {
      throw new Error('Colors must be a non-null object');
    }

    // Cannot overwrite built-in presets
    if (THEME_PRESETS[name]) {
      throw new Error(`Cannot overwrite built-in theme: ${name}`);
    }

    // Validate name for filesystem safety
    if (/[\/\\:*?"<>|]/.test(name)) {
      throw new Error('Theme name contains invalid characters');
    }

    await mkdir(this._themesDir, { recursive: true });

    const theme = {
      name,
      description: description || `Custom theme: ${name}`,
      colors: { ...colors },
    };

    const filePath = join(this._themesDir, `${name}.json`);
    await writeFile(filePath, JSON.stringify(theme, null, 2), 'utf8');

    // Update cache
    this._cache.set(name, this._cloneTheme(theme));

    this.emit('theme-created', this._cloneTheme(theme));

    return this._cloneTheme(theme);
  }

  /**
   * Delete a custom theme file. Cannot delete built-in presets.
   * @param {string} name
   * @returns {Promise<boolean>}
   */
  async deleteTheme(name) {
    if (typeof name !== 'string' || name.length === 0) {
      throw new Error('Theme name must be a non-empty string');
    }

    if (THEME_PRESETS[name]) {
      throw new Error(`Cannot delete built-in theme: ${name}`);
    }

    const filePath = join(this._themesDir, `${name}.json`);

    try {
      await unlink(filePath);
    } catch (err) {
      if (err.code === 'ENOENT') {
        return false;
      }
      throw err;
    }

    // Invalidate cache
    this._cache.delete(name);

    // If the deleted theme was active, deactivate it
    if (this._activeTheme && this._activeTheme.name === name) {
      this._activeTheme = null;
    }

    this.emit('theme-deleted', { name });

    return true;
  }

  // ------------------------------------------------------------------
  // Internals
  // ------------------------------------------------------------------

  /**
   * Load a theme from a JSON file.
   * @param {string} name
   * @returns {Promise<object>}
   */
  async _loadThemeFile(name) {
    const filePath = join(this._themesDir, `${name}.json`);
    const raw = await readFile(filePath, 'utf8');
    const data = JSON.parse(raw);

    if (!data.name || !data.colors) {
      throw new Error(`Invalid theme file: missing name or colors`);
    }

    return {
      name: data.name,
      description: data.description || '',
      colors: { ...data.colors },
    };
  }

  /**
   * Deep-clone a theme object.
   * @param {object} theme
   * @returns {object}
   */
  _cloneTheme(theme) {
    if (!theme) return null;
    return {
      name: theme.name,
      description: theme.description,
      colors: { ...theme.colors },
    };
  }
}

export { ThemeManager };
export default ThemeManager;
