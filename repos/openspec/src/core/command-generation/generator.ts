/**
 * Command Generator
 *
 * Functions for generating command files using tool adapters.
 */

import type { CommandContent, ToolCommandAdapter, GeneratedCommand, InstallContext } from './types.js';

/**
 * Generate a single command file using the provided adapter.
 * @param content - The tool-agnostic command content
 * @param adapter - The tool-specific adapter
 * @param context - Optional install context carrying the resolved scope
 * @returns Generated command with path and file content
 */
export function generateCommand(
  content: CommandContent,
  adapter: ToolCommandAdapter,
  context?: InstallContext
): GeneratedCommand {
  return {
    path: adapter.getFilePath(content.id, context),
    fileContent: adapter.formatFile(content),
  };
}

/**
 * Generate multiple command files using the provided adapter.
 * @param contents - Array of tool-agnostic command contents
 * @param adapter - The tool-specific adapter
 * @param context - Optional install context carrying the resolved scope
 * @returns Array of generated commands with paths and file contents
 */
export function generateCommands(
  contents: CommandContent[],
  adapter: ToolCommandAdapter,
  context?: InstallContext
): GeneratedCommand[] {
  return contents.map((content) => generateCommand(content, adapter, context));
}
