/**
 * Codex Command Adapter
 *
 * Formats commands for Codex following its frontmatter specification.
 * Codex custom prompts can live in either global or project scope:
 *   - Global (default): <CODEX_HOME>/prompts/opsx-<id>.md (absolute path)
 *   - Project: .codex/prompts/opsx-<id>.md (relative path)
 *
 * When no install context is provided, defaults to global scope for
 * backward compatibility with existing behavior.
 *
 * The CODEX_HOME env var can override the default ~/.codex location
 * for global scope.
 */

import os from 'os';
import path from 'path';
import type { CommandContent, ToolCommandAdapter, InstallContext } from '../types.js';

/**
 * Returns the Codex home directory.
 * Respects the CODEX_HOME env var, defaulting to ~/.codex.
 */
function getCodexHome(): string {
  const envHome = process.env.CODEX_HOME?.trim();
  return path.resolve(envHome ? envHome : path.join(os.homedir(), '.codex'));
}

/**
 * Codex adapter for command generation.
 * File path (global, default): <CODEX_HOME>/prompts/opsx-<id>.md (absolute)
 * File path (project): .codex/prompts/opsx-<id>.md (relative)
 * Frontmatter: description, argument-hint
 */
export const codexAdapter: ToolCommandAdapter = {
  toolId: 'codex',

  getFilePath(commandId: string, context?: InstallContext): string {
    const fileName = `opsx-${commandId}.md`;
    // Default to global when no context provided (backward compat)
    if (!context || context.scope === 'global') {
      return path.join(getCodexHome(), 'prompts', fileName);
    }
    // Project scope: relative path
    return path.join('.codex', 'prompts', fileName);
  },

  formatFile(content: CommandContent): string {
    return `---
description: ${content.description}
argument-hint: command arguments
---

${content.body}
`;
  },
};
