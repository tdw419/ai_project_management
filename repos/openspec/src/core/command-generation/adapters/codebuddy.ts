/**
 * CodeBuddy Command Adapter
 *
 * Formats commands for CodeBuddy following its frontmatter specification.
 */

import path from 'path';
import type { CommandContent, ToolCommandAdapter, InstallContext } from '../types.js';

/**
 * CodeBuddy adapter for command generation.
 * File path: .codebuddy/commands/opsx/<id>.md
 * Frontmatter: name, description, argument-hint
 */
export const codebuddyAdapter: ToolCommandAdapter = {
  toolId: 'codebuddy',

  getFilePath(commandId: string, _context?: InstallContext): string {
    return path.join('.codebuddy', 'commands', 'opsx', `${commandId}.md`);
  },

  formatFile(content: CommandContent): string {
    return `---
name: ${content.name}
description: "${content.description}"
argument-hint: "[command arguments]"
---

${content.body}
`;
  },
};
