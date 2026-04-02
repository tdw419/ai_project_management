/**
 * theme-editor.js
 * Theme editing and preset definitions for the CMS theme system.
 */

const THEME_PRESETS = {
  default: {
    name: 'default',
    description: 'Default ASCII World theme',
    colors: {
      active: '#00ff00',
      idle: '#333333',
      critical: '#ff0000',
      border: '#666666',
      text: '#cccccc',
      background: '#0a0a0a',
      accent: '#00aaff',
      warning: '#ffaa00',
      success: '#00ff88',
      header: '#ffffff',
      muted: '#555555',
    },
  },
  'dark-pro': {
    name: 'dark-pro',
    description: 'Dark professional theme with subtle highlights',
    colors: {
      active: '#4ec9b0',
      idle: '#3e3e42',
      critical: '#f44747',
      border: '#4a4a4f',
      text: '#d4d4d4',
      background: '#1e1e1e',
      accent: '#569cd6',
      warning: '#dcdcaa',
      success: '#6a9955',
      header: '#ffffff',
      muted: '#808080',
    },
  },
  cyberpunk: {
    name: 'cyberpunk',
    description: 'Neon-drenched cyberpunk aesthetic',
    colors: {
      active: '#ff00ff',
      idle: '#1a0033',
      critical: '#ff0066',
      border: '#ff00ff',
      text: '#00ffff',
      background: '#0d001a',
      accent: '#ff6600',
      warning: '#ffff00',
      success: '#39ff14',
      header: '#ff00ff',
      muted: '#6633cc',
    },
  },
  'retro-green': {
    name: 'retro-green',
    description: 'Classic phosphor green CRT terminal',
    colors: {
      active: '#33ff00',
      idle: '#003300',
      critical: '#ff3300',
      border: '#1a8c00',
      text: '#33ff00',
      background: '#001a00',
      accent: '#66ff33',
      warning: '#cccc00',
      success: '#33ff00',
      header: '#66ff33',
      muted: '#196600',
    },
  },
  minimal: {
    name: 'minimal',
    description: 'Clean minimal grayscale theme',
    colors: {
      active: '#ffffff',
      idle: '#2a2a2a',
      critical: '#ff4444',
      border: '#444444',
      text: '#aaaaaa',
      background: '#111111',
      accent: '#888888',
      warning: '#ccaa44',
      success: '#88cc88',
      header: '#dddddd',
      muted: '#666666',
    },
  },
  solarized: {
    name: 'solarized',
    description: 'Ethan Schoonover Solarized palette',
    colors: {
      active: '#859900',
      idle: '#073642',
      critical: '#dc322f',
      border: '#586e75',
      text: '#839496',
      background: '#002b36',
      accent: '#268bd2',
      warning: '#b58900',
      success: '#859900',
      header: '#eee8d5',
      muted: '#586e75',
    },
  },
  midnight: {
    name: 'midnight',
    description: 'Deep midnight blue with cool accents',
    colors: {
      active: '#7aa2f7',
      idle: '#1a1b2e',
      critical: '#f7768e',
      border: '#3b3d57',
      text: '#a9b1d6',
      background: '#0f0f1e',
      accent: '#7aa2f7',
      warning: '#e0af68',
      success: '#9ece6a',
      header: '#c0caf5',
      muted: '#565f89',
    },
  },
};

const DEFAULT_THEME = { ...THEME_PRESETS.default };

const BORDER_CHARS = {
  single: { tl: '┌', tr: '┐', bl: '└', br: '┘', h: '─', v: '│' },
  double: { tl: '╔', tr: '╗', bl: '╚', br: '╝', h: '═', v: '║' },
  rounded: { tl: '╭', tr: '╮', bl: '╰', br: '╯', h: '─', v: '│' },
  ascii: { tl: '+', tr: '+', bl: '+', br: '+', h: '-', v: '|' },
  heavy: { tl: '┏', tr: '┓', bl: '┗', br: '┛', h: '━', v: '┃' },
};

class ThemeEditor {
  constructor(options = {}) {
    this.currentTheme = { ...DEFAULT_THEME };
    this.presets = { ...THEME_PRESETS };
  }

  setColors(colors) {
    Object.assign(this.currentTheme.colors, colors);
  }

  getColor(key) {
    return this.currentTheme.colors[key];
  }

  reset() {
    this.currentTheme = { ...DEFAULT_THEME };
  }
}

export { THEME_PRESETS, DEFAULT_THEME, BORDER_CHARS, ThemeEditor };
export default ThemeEditor;
