import type { ChangeMetadata } from '../artifact-graph/types.js';
import type { ValidationIssue } from './types.js';

/**
 * A map of active change names to their metadata.
 */
export type ChangeMap = Record<string, ChangeMetadata>;

/**
 * Result of stack-aware validation across active changes.
 */
export interface StackValidationResult {
  /** Issues found (mix of ERROR and WARNING levels) */
  issues: ValidationIssue[];
  /** Whether validation passes (no ERROR-level issues) */
  valid: boolean;
}

/**
 * Detect dependency cycles in a set of active changes.
 *
 * Uses DFS with coloring (WHITE=unvisited, GRAY=in-progress, BLACK=done)
 * to find back-edges which indicate cycles. Produces a deterministic
 * error for each cycle found, sorted by the cycle's lexicographically
 * smallest representation.
 */
export function detectCycles(changes: ChangeMap): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const names = Object.keys(changes).sort();

  // Color map: undefined = WHITE, true = GRAY, false = BLACK
  const color: Record<string, boolean | undefined> = {};

  // Collect all found cycles as sorted tuples to deduplicate
  const foundCycles = new Set<string>();

  function dfs(node: string, path: string[]): void {
    color[node] = true; // GRAY
    const deps = changes[node]?.dependsOn ?? [];
    for (const dep of deps) {
      // Only follow edges within the known change set
      if (!(dep in changes)) continue;

      if (color[dep] === true) {
        // Back-edge found → cycle
        const cycleStart = path.indexOf(dep);
        const cycle = [...path.slice(cycleStart), dep].sort();
        foundCycles.add(cycle.join(' → '));
      } else if (color[dep] === undefined) {
        dfs(dep, [...path, dep]);
      }
    }
    color[node] = false; // BLACK
  }

  for (const name of names) {
    if (color[name] === undefined) {
      dfs(name, [name]);
    }
  }

  for (const cycleStr of Array.from(foundCycles).sort()) {
    issues.push({
      level: 'ERROR',
      path: 'dependsOn',
      message: `Dependency cycle detected: ${cycleStr}`,
    });
  }

  return issues;
}

/**
 * Detect missing `dependsOn` targets — references to change names that
 * do not exist in the active change set.
 */
export function detectMissingDependencies(changes: ChangeMap): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const names = Object.keys(changes).sort();

  for (const name of names) {
    const deps = changes[name]?.dependsOn ?? [];
    for (const dep of deps) {
      if (!(dep in changes)) {
        issues.push({
          level: 'ERROR',
          path: `${name}/dependsOn`,
          message: `Change '${name}' depends on '${dep}', which does not exist in active changes`,
        });
      }
    }
  }

  return issues;
}

/**
 * Detect changes that are transitively blocked by unresolved or cyclic
 * dependency paths. A change is blocked if any of its `dependsOn` targets
 * either have a dependency error (missing or cyclic) or are themselves blocked.
 */
export function detectBlockedChanges(
  changes: ChangeMap,
  existingErrors: ValidationIssue[]
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // Collect change names that have direct dependency errors
  const errorChanges = new Set<string>();
  for (const issue of existingErrors) {
    // Match patterns like "change-name/dependsOn" or just "dependsOn"
    const match = issue.path.match(/^(.+)\/dependsOn$/);
    if (match) {
      errorChanges.add(match[1]);
    }
  }

  // If there are cycles, all changes in cycles are errored
  for (const issue of existingErrors) {
    if (issue.message.includes('Dependency cycle detected:')) {
      // Extract all change names from the cycle string (they're between arrows)
      // The cycle string looks like "a → b → c" (sorted)
      // We need the original cycle participants; mark all that appear
      const parts = issue.message.replace('Dependency cycle detected: ', '').split(' → ');
      for (const p of parts) {
        errorChanges.add(p.trim());
      }
    }
  }

  // Build blocked set transitively
  const blocked = new Set<string>(errorChanges);
  let changed = true;
  while (changed) {
    changed = false;
    for (const name of Object.keys(changes)) {
      if (blocked.has(name)) continue;
      const deps = changes[name]?.dependsOn ?? [];
      for (const dep of deps) {
        if (blocked.has(dep) || !(dep in changes)) {
          blocked.add(name);
          changed = true;
          break;
        }
      }
    }
  }

  // Report blocked changes that aren't already directly errored
  const names = Object.keys(changes).sort();
  for (const name of names) {
    if (blocked.has(name) && !errorChanges.has(name)) {
      // Find which dependency is the blocker
      const deps = changes[name]?.dependsOn ?? [];
      const blocker = deps.find(d => blocked.has(d) || !(d in changes));
      const blockerMsg = blocker
        ? (blocker in changes ? `'${blocker}' has unresolved dependencies` : `'${blocker}' does not exist`)
        : 'has blocked dependency path';

      issues.push({
        level: 'ERROR',
        path: `${name}/dependsOn`,
        message: `Change '${name}' is transitively blocked: ${blockerMsg}`,
      });
    }
  }

  return issues;
}

/**
 * Detect overlap warnings for active changes that touch the same
 * capability or spec areas. Two changes overlap if:
 * - They share entries in `touches` (same file paths)
 * - They share entries in `provides` (same capabilities)
 */
export function detectOverlapWarnings(changes: ChangeMap): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const names = Object.keys(changes).sort();

  // Check touches overlap
  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      const a = changes[names[i]];
      const b = changes[names[j]];

      // Touches overlap
      const touchesA = a.touches ?? [];
      const touchesB = b.touches ?? [];
      const sharedTouches = touchesA.filter(t => touchesB.includes(t));
      if (sharedTouches.length > 0) {
        issues.push({
          level: 'WARNING',
          path: `${names[i]}/touches`,
          message: `Changes '${names[i]}' and '${names[j]}' both touch: ${sharedTouches.sort().join(', ')}`,
        });
      }

      // Provides overlap (same capability provided by multiple changes)
      const providesA = a.provides ?? [];
      const providesB = b.provides ?? [];
      const sharedProvides = providesA.filter(p => providesB.includes(p));
      if (sharedProvides.length > 0) {
        issues.push({
          level: 'WARNING',
          path: `${names[i]}/provides`,
          message: `Changes '${names[i]}' and '${names[j]}' both provide: ${sharedProvides.sort().join(', ')}`,
        });
      }
    }
  }

  return issues;
}

/**
 * Emit advisory warnings for unmatched `requires` markers — capabilities
 * that a change requires but no active change (or the change itself) provides.
 */
export function detectUnmatchedRequires(changes: ChangeMap): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // Collect all provided capabilities across all active changes
  const allProvides = new Set<string>();
  for (const meta of Object.values(changes)) {
    for (const p of meta.provides ?? []) {
      allProvides.add(p);
    }
  }

  const names = Object.keys(changes).sort();
  for (const name of names) {
    const requires = changes[name]?.requires ?? [];
    for (const req of requires) {
      if (!allProvides.has(req)) {
        issues.push({
          level: 'WARNING',
          path: `${name}/requires`,
          message: `Change '${name}' requires '${req}', but no active change provides it`,
        });
      }
    }
  }

  return issues;
}

/**
 * Run all stack-aware validations across a set of active changes.
 *
 * Returns a combined result with all issues and a `valid` flag that is
 * `false` if any ERROR-level issues are present.
 */
export function validateStack(changes: ChangeMap): StackValidationResult {
  const issues: ValidationIssue[] = [];

  // Phase 1: Structural errors (cycles and missing deps)
  const cycleIssues = detectCycles(changes);
  issues.push(...cycleIssues);

  const missingDepIssues = detectMissingDependencies(changes);
  issues.push(...missingDepIssues);

  // Phase 2: Transitive blocking (depends on phase 1 results)
  const blockedIssues = detectBlockedChanges(changes, [...cycleIssues, ...missingDepIssues]);
  issues.push(...blockedIssues);

  // Phase 3: Advisory warnings (overlap and unmatched requires)
  const overlapIssues = detectOverlapWarnings(changes);
  issues.push(...overlapIssues);

  const unmatchedRequiresIssues = detectUnmatchedRequires(changes);
  issues.push(...unmatchedRequiresIssues);

  const valid = !issues.some(i => i.level === 'ERROR');

  return { issues, valid };
}

/**
 * Result of topological sorting: ordered list of change IDs from
 * earliest (no deps) to latest, or an error if the graph has cycles.
 */
export interface TopologicalSortResult {
  order: string[];
  cycleDetected: boolean;
}

/**
 * Topologically sort changes by their `dependsOn` edges.
 *
 * Uses Kahn's algorithm with a min-heap (lexicographic) for deterministic
 * tie-breaking. Changes with no dependencies come first; changes that
 * depend on others come later. External (non-existent) dependency references
 * are ignored for ordering purposes.
 *
 * Returns `{ order, cycleDetected }`. When `cycleDetected` is true, `order`
 * contains only the changes that could be placed before the cycle was hit
 * (partial result).
 */
export function topologicalSort(changes: ChangeMap): TopologicalSortResult {
  const names = Object.keys(changes);
  if (names.length === 0) return { order: [], cycleDetected: false };

  // Build adjacency list and in-degree map
  const inDegree: Record<string, number> = {};
  const dependents: Record<string, string[]> = {};

  for (const name of names) {
    inDegree[name] = 0;
    dependents[name] = [];
  }

  for (const name of names) {
    const deps = changes[name]?.dependsOn ?? [];
    for (const dep of deps) {
      // Only count edges within the known change set
      if (dep in changes) {
        inDegree[name]++;
        dependents[dep].push(name);
      }
    }
  }

  // Min-heap for deterministic lexicographic tie-breaking
  // Simple array-based approach: sort and pop smallest
  let queue: string[] = names.filter(n => inDegree[n] === 0).sort();
  const order: string[] = [];

  while (queue.length > 0) {
    // Pick lexicographically smallest
    const current = queue.shift()!;
    order.push(current);

    // Process dependents
    const newlyReady: string[] = [];
    for (const dep of dependents[current]) {
      inDegree[dep]--;
      if (inDegree[dep] === 0) {
        newlyReady.push(dep);
      }
    }

    // Insert newly ready nodes in sorted position (maintain sorted queue)
    if (newlyReady.length > 0) {
      newlyReady.sort();
      // Merge two sorted arrays
      const merged: string[] = [];
      let i = 0;
      let j = 0;
      while (i < queue.length && j < newlyReady.length) {
        if (queue[i] <= newlyReady[j]) {
          merged.push(queue[i++]);
        } else {
          merged.push(newlyReady[j++]);
        }
      }
      while (i < queue.length) merged.push(queue[i++]);
      while (j < newlyReady.length) merged.push(newlyReady[j++]);
      queue = merged;
    }
  }

  const cycleDetected = order.length < names.length;
  return { order, cycleDetected };
}
