/**
 * Install Scope Resolver
 *
 * Shared utilities for resolving effective install scope per tool surface.
 * Uses tool capability metadata (scopeSupport) and the user's preferred scope
 * to compute deterministic install targets with fallback/error behavior.
 */

import { AI_TOOLS, type InstallScope, type ToolInstallScopeSupport } from '../config.js';

/**
 * Which artifact surface to resolve scope for.
 */
export type Surface = 'skills' | 'commands';

/**
 * Result of resolving the effective scope for a single tool/surface pair.
 */
export interface ScopeResolution {
  /** The tool id this resolution applies to */
  toolId: string;
  /** The surface (skills or commands) */
  surface: Surface;
  /** The scope the user requested */
  preferredScope: InstallScope;
  /** The scope that will actually be used */
  effectiveScope: InstallScope;
  /** Whether the effective scope differs from the preferred scope */
  fellBack: boolean;
  /** Human-readable reason when fellBack is true */
  fallbackReason?: string;
}

/**
 * Error thrown when scope resolution fails (no supported scope).
 */
export class ScopeResolutionError extends Error {
  public readonly toolId: string;
  public readonly surface: Surface;
  public readonly preferredScope: InstallScope;

  constructor(toolId: string, surface: Surface, preferredScope: InstallScope) {
    const message = scopeResolutionErrorMessage(toolId, surface, preferredScope);
    super(message);
    this.name = 'ScopeResolutionError';
    this.toolId = toolId;
    this.surface = surface;
    this.preferredScope = preferredScope;
  }
}

/**
 * Build a human-readable error message for a failed scope resolution.
 */
export function scopeResolutionErrorMessage(
  toolId: string,
  surface: Surface,
  preferredScope: InstallScope
): string {
  return (
    `Tool "${toolId}" does not support any install scope for ${surface}. ` +
    `Preferred scope was "${preferredScope}". ` +
    `Check that the tool's scopeSupport metadata includes at least one supported scope.`
  );
}

/**
 * Get the supported scopes for a given tool surface.
 *
 * Returns `['project']` (conservative default) when:
 * - The tool is not found in AI_TOOLS
 * - scopeSupport metadata is absent entirely
 * - scopeSupport is present but the surface key is missing
 *
 * This ensures backward compatibility: tools without explicit scope metadata
 * are treated as project-only, which matches current behavior.
 */
export function getSupportedScopes(toolId: string, surface: Surface): InstallScope[] {
  const tool = AI_TOOLS.find((t) => t.value === toolId);

  if (!tool?.scopeSupport) {
    return ['project'];
  }

  const surfaceScopes = tool.scopeSupport[surface];
  if (surfaceScopes === undefined) {
    // Surface key missing from scopeSupport -> conservative project-only default
    return ['project'];
  }

  // Surface key present (may be empty array -> no supported scopes -> will cause hard-fail)
  return surfaceScopes;
}

/**
 * Resolve the effective scope for a single tool/surface pair.
 *
 * Resolution rules (per design.md section 2):
 * 1. If scope support metadata is absent for a tool surface, treat it as
 *    project-only support for conservative backward compatibility.
 * 2. Try preferred scope.
 * 3. If unsupported, use alternate scope when supported.
 * 4. If neither is supported, throw ScopeResolutionError.
 */
export function resolveScope(
  toolId: string,
  surface: Surface,
  preferredScope: InstallScope
): ScopeResolution {
  const supported = getSupportedScopes(toolId, surface);
  const alternate: InstallScope = preferredScope === 'global' ? 'project' : 'global';

  // Rule 2: try preferred scope first
  if (supported.includes(preferredScope)) {
    return {
      toolId,
      surface,
      preferredScope,
      effectiveScope: preferredScope,
      fellBack: false,
    };
  }

  // Rule 3: try alternate scope
  if (supported.includes(alternate)) {
    return {
      toolId,
      surface,
      preferredScope,
      effectiveScope: alternate,
      fellBack: true,
      fallbackReason: `Tool "${toolId}" does not support "${preferredScope}" scope for ${surface}; fell back to "${alternate}".`,
    };
  }

  // Rule 4: neither supported — hard fail
  throw new ScopeResolutionError(toolId, surface, preferredScope);
}

/**
 * Resolve effective scope for a tool across both surfaces (skills and commands).
 *
 * Returns a record keyed by surface with the resolution result for each.
 */
export function resolveScopeForTool(
  toolId: string,
  preferredScope: InstallScope
): Record<Surface, ScopeResolution> {
  return {
    skills: resolveScope(toolId, 'skills', preferredScope),
    commands: resolveScope(toolId, 'commands', preferredScope),
  };
}

/**
 * Resolve effective scope for multiple tools at once.
 *
 * Returns a flat array of resolutions (one per tool per surface).
 * Throws on the first failure encountered.
 */
export function resolveScopeForTools(
  toolIds: string[],
  preferredScope: InstallScope
): ScopeResolution[] {
  const results: ScopeResolution[] = [];

  for (const toolId of toolIds) {
    const perTool = resolveScopeForTool(toolId, preferredScope);
    results.push(perTool.skills, perTool.commands);
  }

  return results;
}
