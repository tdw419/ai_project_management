/**
 * Command Surface Capability Resolver
 *
 * Determines how each tool exposes OpenSpec workflows as commands.
 * Resolution order:
 *   1. Explicit `commandSurface` override on the tool metadata
 *   2. Adapter presence in the CommandAdapterRegistry → `adapter`
 *   3. Has `skillsDir` but no adapter → `skills-invocable`
 *   4. No skillsDir and no adapter → `none`
 */

import { AI_TOOLS, type CommandSurface } from '../config.js';

/**
 * Resolve the effective command surface for a tool.
 *
 * @param toolId       – tool identifier (e.g. 'claude', 'trae')
 * @param hasAdapter   – whether the tool has a registered command adapter
 * @returns The resolved CommandSurface value
 */
export function resolveCommandSurface(toolId: string, hasAdapter: boolean): CommandSurface {
  const tool = AI_TOOLS.find((t) => t.value === toolId);

  // Step 1: explicit override wins
  if (tool?.commandSurface) {
    return tool.commandSurface;
  }

  // Step 2: adapter presence → adapter
  if (hasAdapter) {
    return 'adapter';
  }

  // Step 3: has skillsDir but no adapter → skills-invocable
  if (tool?.skillsDir) {
    return 'skills-invocable';
  }

  // Step 4: nothing → none
  return 'none';
}

/**
 * Resolve command surfaces for multiple tools at once.
 *
 * @param toolIds      – list of tool identifiers
 * @param adapterCheck – function that returns true when a tool has a registered adapter
 * @returns Map of toolId → CommandSurface
 */
export function resolveCommandSurfaces(
  toolIds: string[],
  adapterCheck: (toolId: string) => boolean
): Map<string, CommandSurface> {
  const results = new Map<string, CommandSurface>();
  for (const toolId of toolIds) {
    results.set(toolId, resolveCommandSurface(toolId, adapterCheck(toolId)));
  }
  return results;
}

/**
 * Check whether a command surface supports commands delivery.
 * Only `adapter` and `skills-invocable` surfaces can operate under `delivery=commands`.
 */
export function supportsCommandsDelivery(surface: CommandSurface): boolean {
  return surface === 'adapter' || surface === 'skills-invocable';
}
