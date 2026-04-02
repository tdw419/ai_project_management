/**
 * Topological sorting for change dependency graphs.
 *
 * Provides:
 * - topologicalSort: deterministic dependency order (lexicographic tie-breaking)
 * - getUnblockedChanges: changes ready to start, ordered by recommended sequence
 */

import type { ChangeEntry } from './stack-validator.js';
import { validateChangeStack } from './stack-validator.js';

export interface GraphNode {
  id: string;
  depth: number;
  dependsOn: string[];
}

export interface GraphResult {
  nodes: GraphNode[];
  /** Cycle error message if the graph contains a cycle */
  cycleError: string | null;
}

/**
 * Build a dependency graph and return nodes in topological order.
 *
 * Ordering rules:
 * 1. Changes with no dependencies come first (depth 0)
 * 2. Changes are ordered by depth (ascending)
 * 3. At equal depth, changes are sorted lexicographically by ID
 *
 * If the graph contains a cycle, returns a cycleError and no ordering.
 */
export function topologicalSort(changes: ChangeEntry[]): GraphResult {
  // Validate for cycles first (per proposal: graph validates for cycles first)
  const validation = validateChangeStack(changes);
  const cycleError = validation.errors.find(e => e.message.includes('cycle'));
  if (cycleError) {
    return { nodes: [], cycleError: cycleError.message };
  }

  const changeMap = new Map<string, ChangeEntry>();
  for (const c of changes) {
    changeMap.set(c.id, c);
  }

  // Compute depth for each change (0 = no deps, otherwise max depth of deps + 1)
  const depthCache = new Map<string, number>();
  const visiting = new Set<string>();

  function getDepth(id: string): number {
    if (depthCache.has(id)) return depthCache.get(id)!;
    if (visiting.has(id)) return 0; // Shouldn't happen since we already checked cycles
    const entry = changeMap.get(id);
    if (!entry) return 0;

    visiting.add(id);
    const deps = entry.metadata.dependsOn ?? [];
    let depth = 0;
    for (const dep of deps) {
      // Only consider deps that exist in the active set
      if (changeMap.has(dep)) {
        depth = Math.max(depth, getDepth(dep) + 1);
      }
    }
    visiting.delete(id);
    depthCache.set(id, depth);
    return depth;
  }

  const nodes: GraphNode[] = changes.map(c => ({
    id: c.id,
    depth: getDepth(c.id),
    dependsOn: (c.metadata.dependsOn ?? []).filter(d => changeMap.has(d)),
  }));

  // Sort by depth ascending, then lexicographically by ID for deterministic tie-breaking
  nodes.sort((a, b) => {
    if (a.depth !== b.depth) return a.depth - b.depth;
    return a.id.localeCompare(b.id);
  });

  return { nodes, cycleError: null };
}

/**
 * Get the set of unblocked changes — those whose all dependencies are satisfied.
 *
 * Returns changes sorted by recommended execution order:
 * 1. Depth ascending (shallower deps first = foundational work)
 * 2. Lexicographic by ID at equal depth
 *
 * A change is "unblocked" when ALL of its dependsOn targets exist in the provided set.
 */
export function getUnblockedChanges(changes: ChangeEntry[]): GraphResult {
  // Validate for cycles first
  const validation = validateChangeStack(changes);
  const cycleError = validation.errors.find(e => e.message.includes('cycle'));
  if (cycleError) {
    return { nodes: [], cycleError: cycleError.message };
  }

  const knownIds = new Set(changes.map(c => c.id));

  // Compute depth for sorting (shared with topologicalSort logic)
  const changeMap = new Map<string, ChangeEntry>();
  for (const c of changes) {
    changeMap.set(c.id, c);
  }

  // Determine which changes are truly unblocked:
  // A change is blocked if ANY of its deps are missing from the active set,
  // OR if any of its deps are themselves blocked (transitive blocking).
  const blockedCache = new Map<string, boolean>();

  function isBlocked(id: string, visiting: Set<string>): boolean {
    if (blockedCache.has(id)) return blockedCache.get(id)!;
    if (visiting.has(id)) return false; // cycle already handled above
    const entry = changeMap.get(id);
    if (!entry) return true; // unknown dep

    visiting.add(id);
    const deps = entry.metadata.dependsOn ?? [];
    for (const dep of deps) {
      if (!knownIds.has(dep)) {
        // Missing dep -> this change is blocked
        blockedCache.set(id, true);
        visiting.delete(id);
        return true;
      }
      if (isBlocked(dep, visiting)) {
        // Dep is blocked -> this change is transitively blocked
        blockedCache.set(id, true);
        visiting.delete(id);
        return true;
      }
    }
    visiting.delete(id);
    blockedCache.set(id, false);
    return false;
  }

  const depthCache = new Map<string, number>();
  const depthVisiting = new Set<string>();

  function getDepth(id: string): number {
    if (depthCache.has(id)) return depthCache.get(id)!;
    if (depthVisiting.has(id)) return 0;
    const entry = changeMap.get(id);
    if (!entry) return 0;

    depthVisiting.add(id);
    const deps = entry.metadata.dependsOn ?? [];
    let depth = 0;
    for (const dep of deps) {
      if (changeMap.has(dep)) {
        depth = Math.max(depth, getDepth(dep) + 1);
      }
    }
    depthVisiting.delete(id);
    depthCache.set(id, depth);
    return depth;
  }

  // Collect unblocked changes
  const emptyVisiting = new Set<string>();
  const nodes: GraphNode[] = [];
  for (const c of changes) {
    if (!isBlocked(c.id, new Set(emptyVisiting))) {
      const deps = (c.metadata.dependsOn ?? []).filter(d => knownIds.has(d));
      nodes.push({
        id: c.id,
        depth: getDepth(c.id),
        dependsOn: deps,
      });
    }
  }

  // Sort: depth ascending, then lexicographic by ID
  nodes.sort((a, b) => {
    if (a.depth !== b.depth) return a.depth - b.depth;
    return a.id.localeCompare(b.id);
  });

  return { nodes, cycleError: null };
}
