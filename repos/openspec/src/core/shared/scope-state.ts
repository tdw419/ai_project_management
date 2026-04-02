/**
 * Scope State Persistence
 *
 * Tracks the last successful effective install scope per tool/surface pair.
 * Used for deterministic scope-drift detection: if the effective scope changes
 * between runs, the update command knows it must clean old targets and write
 * to new ones.
 *
 * State is stored in the global openspec data directory alongside other user data.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { getGlobalDataDir } from '../global-config.js';
import type { InstallScope } from '../config.js';
import type { Surface } from './scope-resolver.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Persistent record of the last effective scope per tool/surface pair.
 * Key format: "<toolId>::<surface>" (e.g., "codex::commands").
 */
export type ScopeStateMap = Record<string, InstallScope>;

// ---------------------------------------------------------------------------
// File helpers
// ---------------------------------------------------------------------------

const SCOPE_STATE_FILENAME = 'scope-state.json';

function getScopeStatePath(): string {
  return path.join(getGlobalDataDir(), SCOPE_STATE_FILENAME);
}

/**
 * Build the map key for a tool/surface pair.
 */
export function scopeStateKey(toolId: string, surface: Surface): string {
  return `${toolId}::${surface}`;
}

// ---------------------------------------------------------------------------
// Read / Write
// ---------------------------------------------------------------------------

/**
 * Load the scope state from disk.
 * Returns an empty map when the file does not exist or is invalid.
 */
export function loadScopeState(): ScopeStateMap {
  const filePath = getScopeStatePath();
  try {
    if (!fs.existsSync(filePath)) {
      return {};
    }
    const raw = fs.readFileSync(filePath, 'utf-8');
    const parsed = JSON.parse(raw);
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as ScopeStateMap;
    }
    return {};
  } catch {
    return {};
  }
}

/**
 * Persist the scope state to disk.
 * Creates the data directory if it does not exist.
 */
export function saveScopeState(state: ScopeStateMap): void {
  const dir = getGlobalDataDir();
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(getScopeStatePath(), JSON.stringify(state, null, 2) + '\n', 'utf-8');
}

/**
 * Record the effective scope for a tool/surface pair and persist.
 * Mutates and saves the provided state object.
 */
export function recordEffectiveScope(
  state: ScopeStateMap,
  toolId: string,
  surface: Surface,
  effectiveScope: InstallScope,
): ScopeStateMap {
  const key = scopeStateKey(toolId, surface);
  state[key] = effectiveScope;
  return state;
}

/**
 * Get the previously recorded effective scope for a tool/surface pair.
 * Returns undefined when no record exists.
 */
export function getPreviousScope(
  state: ScopeStateMap,
  toolId: string,
  surface: Surface,
): InstallScope | undefined {
  return state[scopeStateKey(toolId, surface)];
}

/**
 * Detect whether the effective scope has drifted from the previously
 * recorded value for a given tool/surface pair.
 *
 * Returns `true` when:
 * - A previous scope was recorded AND
 * - The previous scope differs from the current effective scope.
 *
 * Returns `false` when there is no previous record (first run) or when
 * the scopes match.
 */
export function hasScopeDrift(
  state: ScopeStateMap,
  toolId: string,
  surface: Surface,
  effectiveScope: InstallScope,
): boolean {
  const prev = getPreviousScope(state, toolId, surface);
  if (prev === undefined) return false;
  return prev !== effectiveScope;
}

/**
 * Bulk-record effective scopes for multiple tool/surface resolutions.
 * Returns the mutated state.
 */
export function recordResolutions(
  state: ScopeStateMap,
  resolutions: Array<{ toolId: string; surface: Surface; effectiveScope: InstallScope }>,
): ScopeStateMap {
  for (const r of resolutions) {
    recordEffectiveScope(state, r.toolId, r.surface, r.effectiveScope);
  }
  return state;
}
