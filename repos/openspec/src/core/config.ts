export const OPENSPEC_DIR_NAME = 'openspec';

export const OPENSPEC_MARKERS = {
  start: '<!-- OPENSPEC:START -->',
  end: '<!-- OPENSPEC:END -->'
};

export interface OpenSpecConfig {
  aiTools: string[];
}

export type InstallScope = 'global' | 'project';

/**
 * Declares which install scopes a tool surface supports.
 * If omitted for a surface, the resolver treats it as project-only.
 */
export interface ToolInstallScopeSupport {
  skills?: InstallScope[];
  commands?: InstallScope[];
}

/**
 * Describes how a tool exposes OpenSpec workflows as invocable commands.
 *
 * - `adapter`         – command files are generated through a registered command adapter
 * - `skills-invocable` – skills are directly invocable as commands (e.g. Trae skill entries)
 * - `none`            – no OpenSpec command surface
 */
export type CommandSurface = 'adapter' | 'skills-invocable' | 'none';

export interface AIToolOption {
  name: string;
  value: string;
  available: boolean;
  successLabel?: string;
  skillsDir?: string; // e.g., '.claude' - /skills suffix per Agent Skills spec
  scopeSupport?: ToolInstallScopeSupport;
  /** Explicit command-surface capability override. When absent, inference is used. */
  commandSurface?: CommandSurface;
}

export const AI_TOOLS: AIToolOption[] = [
  { name: 'Amazon Q Developer', value: 'amazon-q', available: true, successLabel: 'Amazon Q Developer', skillsDir: '.amazonq' },
  { name: 'Antigravity', value: 'antigravity', available: true, successLabel: 'Antigravity', skillsDir: '.agent' },
  { name: 'Auggie (Augment CLI)', value: 'auggie', available: true, successLabel: 'Auggie', skillsDir: '.augment' },
  { name: 'Claude Code', value: 'claude', available: true, successLabel: 'Claude Code', skillsDir: '.claude' },
  { name: 'Cline', value: 'cline', available: true, successLabel: 'Cline', skillsDir: '.cline' },
  { name: 'Codex', value: 'codex', available: true, successLabel: 'Codex', skillsDir: '.codex', scopeSupport: { skills: ['project'], commands: ['global', 'project'] } },
  { name: 'CodeBuddy Code (CLI)', value: 'codebuddy', available: true, successLabel: 'CodeBuddy Code', skillsDir: '.codebuddy' },
  { name: 'Continue', value: 'continue', available: true, successLabel: 'Continue (VS Code / JetBrains / Cli)', skillsDir: '.continue' },
  { name: 'CoStrict', value: 'costrict', available: true, successLabel: 'CoStrict', skillsDir: '.cospec' },
  { name: 'Crush', value: 'crush', available: true, successLabel: 'Crush', skillsDir: '.crush' },
  { name: 'Cursor', value: 'cursor', available: true, successLabel: 'Cursor', skillsDir: '.cursor' },
  { name: 'Factory Droid', value: 'factory', available: true, successLabel: 'Factory Droid', skillsDir: '.factory' },
  { name: 'Gemini CLI', value: 'gemini', available: true, successLabel: 'Gemini CLI', skillsDir: '.gemini' },
  { name: 'GitHub Copilot', value: 'github-copilot', available: true, successLabel: 'GitHub Copilot', skillsDir: '.github' },
  { name: 'iFlow', value: 'iflow', available: true, successLabel: 'iFlow', skillsDir: '.iflow' },
  { name: 'Kilo Code', value: 'kilocode', available: true, successLabel: 'Kilo Code', skillsDir: '.kilocode' },
  { name: 'Kiro', value: 'kiro', available: true, successLabel: 'Kiro', skillsDir: '.kiro' },
  { name: 'OpenCode', value: 'opencode', available: true, successLabel: 'OpenCode', skillsDir: '.opencode' },
  { name: 'Pi', value: 'pi', available: true, successLabel: 'Pi', skillsDir: '.pi' },
  { name: 'Qoder', value: 'qoder', available: true, successLabel: 'Qoder', skillsDir: '.qoder' },
  { name: 'Qwen Code', value: 'qwen', available: true, successLabel: 'Qwen Code', skillsDir: '.qwen' },
  { name: 'RooCode', value: 'roocode', available: true, successLabel: 'RooCode', skillsDir: '.roo' },
  { name: 'Trae', value: 'trae', available: true, successLabel: 'Trae', skillsDir: '.trae', commandSurface: 'skills-invocable' },
  { name: 'Windsurf', value: 'windsurf', available: true, successLabel: 'Windsurf', skillsDir: '.windsurf' },
  { name: 'AGENTS.md (works with Amp, VS Code, …)', value: 'agents', available: false, successLabel: 'your AGENTS.md-compatible assistant' }
];
