/**
 * theme-manager.test.js
 * Tests for the CMS ThemeManager.
 * Uses Node.js built-in test runner.
 */

import { describe, it, before, after, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { join, resolve } from 'node:path';
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { ThemeManager } from '../sync/theme-manager.js';
import { THEME_PRESETS } from '../sync/theme-editor.js';
import { PixelFormulaEngine } from '../sync/pixel-formula-engine.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function makeTempDir() {
  return mkdtemp(join(tmpdir(), 'theme-mgr-test-'));
}

// A minimal PixelFormulaEngine-compatible stub
function createEngineStub() {
  const engine = new PixelFormulaEngine();
  return engine;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ThemeManager', () => {
  let tempDir;

  before(async () => {
    tempDir = await makeTempDir();
  });

  after(async () => {
    try {
      await rm(tempDir, { recursive: true, force: true });
    } catch {
      // best effort
    }
  });

  describe('constructor', () => {
    it('should accept default options', () => {
      const mgr = new ThemeManager();
      assert.ok(mgr instanceof ThemeManager);
      assert.equal(mgr._themesDir, resolve('themes'));
      assert.equal(mgr._engine, null);
    });

    it('should accept custom themesDir and pixelFormulaEngine', () => {
      const engine = createEngineStub();
      const mgr = new ThemeManager({ themesDir: tempDir, pixelFormulaEngine: engine });
      assert.equal(mgr._themesDir, tempDir);
      assert.strictEqual(mgr._engine, engine);
    });
  });

  describe('loadTheme', () => {
    it('should load a built-in preset theme', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const theme = await mgr.loadTheme('default');
      assert.equal(theme.name, 'default');
      assert.equal(theme.description, THEME_PRESETS.default.description);
      assert.equal(theme.colors.active, '#00ff00');
    });

    it('should load dark-pro preset', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const theme = await mgr.loadTheme('dark-pro');
      assert.equal(theme.name, 'dark-pro');
      assert.equal(theme.colors.background, '#1e1e1e');
    });

    it('should load cyberpunk preset', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const theme = await mgr.loadTheme('cyberpunk');
      assert.equal(theme.name, 'cyberpunk');
      assert.equal(theme.colors.text, '#00ffff');
    });

    it('should load a theme from a JSON file', async () => {
      const customTheme = {
        name: 'my-custom',
        description: 'A test theme',
        colors: { active: '#aabbcc', idle: '#112233', background: '#000000' },
      };
      await writeFile(
        join(tempDir, 'my-custom.json'),
        JSON.stringify(customTheme),
        'utf8'
      );

      const mgr = new ThemeManager({ themesDir: tempDir });
      const theme = await mgr.loadTheme('my-custom');
      assert.equal(theme.name, 'my-custom');
      assert.equal(theme.colors.active, '#aabbcc');
    });

    it('should throw for empty name', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(() => mgr.loadTheme(''), /non-empty string/);
    });

    it('should throw for non-existent file theme', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(() => mgr.loadTheme('does-not-exist'));
    });

    it('should cache loaded themes', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const t1 = await mgr.loadTheme('default');
      const t2 = await mgr.loadTheme('default');
      assert.deepEqual(t1, t2);
    });
  });

  describe('listThemes', () => {
    it('should list all built-in themes', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const themes = await mgr.listThemes();
      const names = themes.map((t) => t.name);

      // All THEME_PRESETS keys should be present
      for (const presetName of Object.keys(THEME_PRESETS)) {
        assert.ok(names.includes(presetName), `Missing preset: ${presetName}`);
      }
    });

    it('should include file-based themes', async () => {
      const listDir = await makeTempDir();
      const customTheme = {
        name: 'file-theme',
        description: 'From file',
        colors: { active: '#ff0000' },
      };
      await writeFile(
        join(listDir, 'file-theme.json'),
        JSON.stringify(customTheme),
        'utf8'
      );

      const mgr = new ThemeManager({ themesDir: listDir });
      const themes = await mgr.listThemes();
      const found = themes.find((t) => t.name === 'file-theme');
      assert.ok(found, 'file-theme not found in listing');
      assert.equal(found.colors.active, '#ff0000');

      await rm(listDir, { recursive: true, force: true });
    });

    it('should return themes with name, description, colors', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const themes = await mgr.listThemes();
      for (const theme of themes) {
        assert.ok(theme.name, 'theme missing name');
        assert.ok(typeof theme.description === 'string', 'theme missing description');
        assert.ok(theme.colors && typeof theme.colors === 'object', 'theme missing colors');
      }
    });
  });

  describe('getActiveTheme', () => {
    it('should return null initially', () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      assert.equal(mgr.getActiveTheme(), null);
    });

    it('should return the active theme after applyTheme', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await mgr.applyTheme('default');
      const active = mgr.getActiveTheme();
      assert.equal(active.name, 'default');
    });
  });

  describe('applyTheme', () => {
    it('should set active theme', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const applied = await mgr.applyTheme('cyberpunk');
      assert.equal(applied.name, 'cyberpunk');
      assert.equal(mgr.getActiveTheme().name, 'cyberpunk');
    });

    it('should apply palette to pixelFormulaEngine', async () => {
      const engine = createEngineStub();
      const mgr = new ThemeManager({ themesDir: tempDir, pixelFormulaEngine: engine });
      await mgr.applyTheme('solarized');

      const palette = engine.getPalette();
      assert.equal(palette.background, '#002b36');
      assert.equal(palette.accent, '#268bd2');
    });

    it('should emit theme-changed event', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      let eventFired = false;
      let eventData = null;

      mgr.on('theme-changed', (data) => {
        eventFired = true;
        eventData = data;
      });

      await mgr.applyTheme('retro-green');

      assert.ok(eventFired, 'theme-changed event should fire');
      assert.equal(eventData.theme.name, 'retro-green');
      assert.equal(eventData.previous, null);
    });

    it('should include previous theme in event when switching', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      let eventData = null;

      await mgr.applyTheme('default');
      mgr.on('theme-changed', (data) => {
        eventData = data;
      });
      await mgr.applyTheme('midnight');

      assert.equal(eventData.theme.name, 'midnight');
      assert.equal(eventData.previous.name, 'default');
    });

    it('should work without pixelFormulaEngine', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const result = await mgr.applyTheme('minimal');
      assert.equal(result.name, 'minimal');
    });
  });

  describe('createTheme', () => {
    it('should create a new theme file', async () => {
      const createDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: createDir });

      const colors = { active: '#abcdef', background: '#000000' };
      const theme = await mgr.createTheme('my-theme', colors, 'Test theme');

      assert.equal(theme.name, 'my-theme');
      assert.equal(theme.description, 'Test theme');
      assert.equal(theme.colors.active, '#abcdef');

      // Verify it can be loaded back
      const loaded = await mgr.loadTheme('my-theme');
      assert.equal(loaded.name, 'my-theme');

      await rm(createDir, { recursive: true, force: true });
    });

    it('should default description when omitted', async () => {
      const createDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: createDir });

      const theme = await mgr.createTheme('no-desc', { active: '#000' });
      assert.ok(theme.description.includes('no-desc'));

      await rm(createDir, { recursive: true, force: true });
    });

    it('should reject empty name', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(
        () => mgr.createTheme('', { active: '#000' }),
        /non-empty string/
      );
    });

    it('should reject null colors', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(
        () => mgr.createTheme('bad', null),
        /non-null object/
      );
    });

    it('should reject overwriting built-in themes', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(
        () => mgr.createTheme('default', { active: '#000' }),
        /Cannot overwrite built-in/
      );
    });

    it('should reject names with filesystem-unsafe characters', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(
        () => mgr.createTheme('bad/name', { active: '#000' }),
        /invalid characters/
      );
    });

    it('should emit theme-created event', async () => {
      const createDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: createDir });
      let eventTheme = null;

      mgr.on('theme-created', (theme) => {
        eventTheme = theme;
      });

      await mgr.createTheme('event-test', { active: '#123456' });
      assert.ok(eventTheme);
      assert.equal(eventTheme.name, 'event-test');

      await rm(createDir, { recursive: true, force: true });
    });
  });

  describe('deleteTheme', () => {
    it('should delete a custom theme file', async () => {
      const delDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: delDir });

      await mgr.createTheme('to-delete', { active: '#111' });
      const result = await mgr.deleteTheme('to-delete');
      assert.equal(result, true);

      // Verify it's gone
      await assert.rejects(() => mgr.loadTheme('to-delete'));

      await rm(delDir, { recursive: true, force: true });
    });

    it('should return false for non-existent theme', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const result = await mgr.deleteTheme('non-existent-file');
      assert.equal(result, false);
    });

    it('should reject deleting built-in themes', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await assert.rejects(
        () => mgr.deleteTheme('default'),
        /Cannot delete built-in/
      );
    });

    it('should deactivate if the active theme is deleted', async () => {
      const delDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: delDir });

      await mgr.createTheme('will-be-active', { active: '#222' });
      await mgr.applyTheme('will-be-active');
      assert.equal(mgr.getActiveTheme().name, 'will-be-active');

      await mgr.deleteTheme('will-be-active');
      assert.equal(mgr.getActiveTheme(), null);

      await rm(delDir, { recursive: true, force: true });
    });

    it('should emit theme-deleted event', async () => {
      const delDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: delDir });
      let deletedName = null;

      mgr.on('theme-deleted', ({ name }) => {
        deletedName = name;
      });

      await mgr.createTheme('emit-del', { active: '#333' });
      await mgr.deleteTheme('emit-del');

      assert.equal(deletedName, 'emit-del');

      await rm(delDir, { recursive: true, force: true });
    });

    it('should clear cache for deleted theme', async () => {
      const delDir = await makeTempDir();
      const mgr = new ThemeManager({ themesDir: delDir });

      await mgr.createTheme('cached-del', { active: '#444' });
      await mgr.loadTheme('cached-del'); // loads into cache
      await mgr.deleteTheme('cached-del');

      // Cache should be invalidated — loading again should fail
      await assert.rejects(() => mgr.loadTheme('cached-del'));

      await rm(delDir, { recursive: true, force: true });
    });
  });

  describe('isolation / immutability', () => {
    it('should not mutate cached themes on external modification', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      const t1 = await mgr.loadTheme('default');
      t1.colors.active = 'MUTATED';
      t1.name = 'MUTATED';

      const t2 = await mgr.loadTheme('default');
      assert.equal(t2.name, 'default');
      assert.equal(t2.colors.active, '#00ff00');
    });

    it('getActiveTheme should return a clone', async () => {
      const mgr = new ThemeManager({ themesDir: tempDir });
      await mgr.applyTheme('default');
      const active = mgr.getActiveTheme();
      active.colors.active = 'MUTATED';

      const active2 = mgr.getActiveTheme();
      assert.equal(active2.colors.active, '#00ff00');
    });
  });
});
