/**
 * Antigravity Command Adapter
 *
 * Formats commands for Antigravity following its frontmatter specification.
 */

import path from 'path';
import type { CommandContent, ToolCommandAdapter, InstallContext } from '../types.js';

/**
 * Antigravity adapter for command generation.
 * File path: .agent/workflows/opsx-<id>.md
 * Frontmatter: description
 */
export const antigravityAdapter: ToolCommandAdapter = {
  toolId: 'antigravity',

  getFilePath(commandId: string, _context?: InstallContext): string {
    return path.join('.agent', 'workflows', `opsx-${commandId}.md`);
  },

  formatFile(content: CommandContent): string {
    return `---
description: ${content.description}
---

${content.body}
`;
  },
};
