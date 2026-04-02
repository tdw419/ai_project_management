/**
 * Stack-Aware Validation for change dependencies.
 *
 * Validates the dependency graph across active changes:
 * - Dependency cycles (hard error)
 * - Missing dependsOn targets (hard error)
 * - Transitive blocking via unresolved/cyclic paths (hard error)
 * - Overlap warnings when multiple active changes touch the same areas
 * - Advisory warnings for unmatched requires markers
 */

import type { ChangeMetadata } from '../artifact-graph/types.js';
import type { ValidationIssue } from './types.js';

/**
 * A change entry ready for stack validation: its ID plus its parsed metadata.
 */
export interface ChangeEntry {
  id: string;
  metadata: ChangeMetadata;
}

export interface StackValidationResult {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

/**
 * Validate a set of changes for stack-level issues.
 *
 * @param changes - Array of change entries with id and metadata
 * @returns StackValidationResult with errors (hard blockers) and warnings (advisory)
 */
export function validateChangeStack(changes: ChangeEntry[]): StackValidationResult {
  const errors: ValidationIssue[] = [];
  const warnings: ValidationIssue[] = [];

  const changeMap = new Map<string, ChangeMetadata>();
  for (const c of changes) {
    changeMap.set(c.id, c.metadata);
  }

  // 2.1 Detect dependency cycles
  const cycleErrors = detectCycles(changes, changeMap);
  errors.push(...cycleErrors);

  // 2.2 Detect missing dependsOn targets and transitive blocking
  const missingAndBlocked = detectMissingAndBlocked(changes, changeMap);
  errors.push(...missingAndBlocked);

  // 2.3 Overlap warnings for touches
  const overlapWarnings = detectOverlapWarnings(changes);
  warnings.push(...overlapWarnings);

  // 2.4 Advisory warnings for unmatched requires
  const requiresWarnings = detectUnmatchedRequires(changes, changeMap);
  warnings.push(...requiresWarnings);

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

/**
 * 2.1 Detect dependency cycles in the dependsOn graph.
 * Uses DFS with a recursion stack to find back edges.
 * Reports the full cycle path in a deterministic order.
 */
function detectCycles(
  changes: ChangeEntry[],
  changeMap: Map<string, ChangeMetadata>,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // Build adjacency list: change -> its dependsOn targets
  const adj = new Map<string, string[]>();
  for (const c of changes) {
    adj.set(c.id, c.metadata.dependsOn ?? []);
  }

  const visited = new Set<string>();
  const inStack = new Set<string>();
  const parent = new Map<string, string>();

  function dfs(id: string): string[] | null {
    visited.add(id);
    inStack.add(id);

    const deps = adj.get(id) ?? [];
    for (const dep of deps) {
      // Only follow edges within known changes
      if (!changeMap.has(dep)) continue;

      if (!visited.has(dep)) {
        parent.set(dep, id);
        const cycle = dfs(dep);
        if (cycle) return cycle;
      } else if (inStack.has(dep)) {
        // Reconstruct cycle path
        const path = [dep];
        let current = id;
        while (current !== dep) {
          path.unshift(current);
          current = parent.get(current)!;
        }
        path.unshift(dep);
        return path;
      }
    }

    inStack.delete(id);
    return null;
  }

  // Process in sorted order for deterministic output
  const sortedIds = Array.from(changeMap.keys()).sort();
  for (const id of sortedIds) {
    if (!visited.has(id)) {
      const cycle = dfs(id);
      if (cycle) {
        const cycleStr = cycle.join(' -> ');
        issues.push({
          level: 'ERROR',
          path: id,
          message: `Dependency cycle detected: ${cycleStr}`,
        });
        // Report only the first cycle found (deterministic)
        break;
      }
    }
  }

  return issues;
}

/**
 * 2.2 Detect missing dependsOn targets and changes transitively blocked
 * by unresolved/cyclic dependency paths.
 */
function detectMissingAndBlocked(
  changes: ChangeEntry[],
  changeMap: Map<string, ChangeMetadata>,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const knownIds = new Set(changeMap.keys());

  // Detect missing targets
  for (const c of changes) {
    const deps = c.metadata.dependsOn ?? [];
    for (const dep of deps) {
      if (!knownIds.has(dep)) {
        issues.push({
          level: 'ERROR',
          path: c.id,
          message: `Missing dependency: '${dep}' does not exist in active changes`,
        });
      }
    }
  }

  // Detect transitively blocked changes (blocked by an unresolvable dependency)
  // A change is blocked if any of its dependsOn (transitively) has a missing or cyclic dep
  const blocked = new Set<string>();

  function isBlocked(id: string, visiting: Set<string>): boolean {
    if (blocked.has(id)) return true;
    const meta = changeMap.get(id);
    if (!meta) return true; // Unknown = blocked

    const deps = meta.dependsOn ?? [];
    for (const dep of deps) {
      if (!knownIds.has(dep)) {
        blocked.add(id);
        return true;
      }
      // Check for self-reference
      if (dep === id) {
        blocked.add(id);
        return true;
      }
      if (visiting.has(dep)) {
        // Cycle in traversal
        blocked.add(id);
        return true;
      }
      visiting.add(dep);
      if (isBlocked(dep, visiting)) {
        blocked.add(id);
        return true;
      }
      visiting.delete(dep);
    }
    return false;
  }

  for (const c of changes) {
    const visiting = new Set<string>([c.id]);
    if (isBlocked(c.id, visiting)) {
      // Only report if not already reported as a direct missing dep or cycle
      const deps = c.metadata.dependsOn ?? [];
      const hasDirectIssue = deps.some(
        d => !knownIds.has(d) || d === c.id
      );
      // Check if already flagged by cycle detector
      const alreadyFlagged = issues.some(
        i => i.path === c.id && i.message.includes('cycle')
      );
      if (!hasDirectIssue && !alreadyFlagged) {
        issues.push({
          level: 'ERROR',
          path: c.id,
          message: `Change is transitively blocked by unresolvable dependency path`,
        });
      }
    }
  }

  return issues;
}

/**
 * 2.3 Detect overlap warnings for active changes that touch the same areas.
 */
function detectOverlapWarnings(changes: ChangeEntry[]): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const areaMap = new Map<string, string[]>(); // area -> change IDs that touch it

  for (const c of changes) {
    const touches = c.metadata.touches ?? [];
    for (const area of touches) {
      if (!areaMap.has(area)) {
        areaMap.set(area, []);
      }
      areaMap.get(area)!.push(c.id);
    }
  }

  // Sort areas for deterministic output
  const sortedAreas = Array.from(areaMap.keys()).sort();
  for (const area of sortedAreas) {
    const changeIds = areaMap.get(area)!;
    if (changeIds.length > 1) {
      const sortedIds = [...changeIds].sort();
      issues.push({
        level: 'WARNING',
        path: sortedIds.join(', '),
        message: `Overlap: changes ${sortedIds.map(id => `'${id}'`).join(', ')} touch the same area '${area}'`,
      });
    }
  }

  return issues;
}

/**
 * 2.4 Emit advisory warnings for unmatched requires markers.
 * A requires marker is unmatched when no active change provides it.
 */
function detectUnmatchedRequires(
  changes: ChangeEntry[],
  changeMap: Map<string, ChangeMetadata>,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // Collect all provided markers
  const provided = new Set<string>();
  for (const c of changes) {
    const prov = c.metadata.provides ?? [];
    for (const p of prov) {
      provided.add(p);
    }
  }

  // Check each change's requires
  for (const c of changes) {
    const reqs = c.metadata.requires ?? [];
    for (const req of reqs) {
      if (!provided.has(req)) {
        issues.push({
          level: 'WARNING',
          path: c.id,
          message: `Unmatched requires: '${req}' has no provider in active changes`,
        });
      }
    }
  }

  return issues;
}
