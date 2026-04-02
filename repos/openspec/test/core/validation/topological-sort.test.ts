import { describe, it, expect } from 'vitest';
import type { ChangeMetadata } from '../../../src/core/artifact-graph/types.js';
import { topologicalSort } from '../../../src/core/validation/stack-validator.js';

// Helper to build a ChangeMap quickly
function map(entries: Record<string, Partial<ChangeMetadata>>): Record<string, ChangeMetadata> {
  const result: Record<string, ChangeMetadata> = {};
  for (const [name, meta] of Object.entries(entries)) {
    result[name] = {
      schema: meta.schema ?? 'spec-driven',
      ...meta,
    } as ChangeMetadata;
  }
  return result;
}

describe('topologicalSort', () => {
  it('returns empty order for empty change set', () => {
    const result = topologicalSort({});
    expect(result.order).toEqual([]);
    expect(result.cycleDetected).toBe(false);
  });

  it('returns all changes for independent changes (no deps)', () => {
    const changes = map({
      'change-c': {},
      'change-a': {},
      'change-b': {},
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    // No deps → lexicographic tie-breaking
    expect(result.order).toEqual(['change-a', 'change-b', 'change-c']);
  });

  it('orders a simple linear chain correctly', () => {
    const changes = map({
      'change-a': {},
      'change-b': { dependsOn: ['change-a'] },
      'change-c': { dependsOn: ['change-b'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    expect(result.order).toEqual(['change-a', 'change-b', 'change-c']);
  });

  it('orders a diamond dependency correctly', () => {
    const changes = map({
      root: {},
      left: { dependsOn: ['root'] },
      right: { dependsOn: ['root'] },
      merge: { dependsOn: ['left', 'right'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    // root first, then left and right (lexicographic), then merge
    expect(result.order).toEqual(['root', 'left', 'right', 'merge']);
  });

  it('uses lexicographic tie-breaking at equal depth', () => {
    const changes = map({
      'z-change': {},
      'a-change': {},
      'm-change': {},
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    // All at depth 0 → sorted lexicographically
    expect(result.order).toEqual(['a-change', 'm-change', 'z-change']);
  });

  it('uses lexicographic tie-breaking for dependent siblings', () => {
    const changes = map({
      parent: {},
      'child-b': { dependsOn: ['parent'] },
      'child-a': { dependsOn: ['parent'] },
      grandchild: { dependsOn: ['child-a', 'child-b'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    expect(result.order).toEqual(['parent', 'child-a', 'child-b', 'grandchild']);
  });

  it('detects a simple cycle', () => {
    const changes = map({
      'change-a': { dependsOn: ['change-b'] },
      'change-b': { dependsOn: ['change-a'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(true);
    // Neither can be placed
    expect(result.order).toEqual([]);
  });

  it('detects a three-node cycle', () => {
    const changes = map({
      'change-a': { dependsOn: ['change-c'] },
      'change-b': { dependsOn: ['change-a'] },
      'change-c': { dependsOn: ['change-b'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(true);
    expect(result.order).toEqual([]);
  });

  it('returns partial order when some changes are in a cycle', () => {
    const changes = map({
      'free-a': {},
      'free-b': {},
      'cycle-x': { dependsOn: ['cycle-y'] },
      'cycle-y': { dependsOn: ['cycle-x'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(true);
    // free-a and free-b should be in order, cycle nodes excluded
    expect(result.order).toEqual(['free-a', 'free-b']);
  });

  it('returns partial order with a change depending on a cycle', () => {
    const changes = map({
      root: {},
      'cycle-a': { dependsOn: ['cycle-b'] },
      'cycle-b': { dependsOn: ['cycle-a'] },
      dependent: { dependsOn: ['cycle-a'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(true);
    // Only root can be placed
    expect(result.order).toEqual(['root']);
  });

  it('ignores external dependency references for ordering', () => {
    const changes = map({
      'change-a': { dependsOn: ['nonexistent'] },
      'change-b': {},
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    // 'nonexistent' not in set, so change-a has no in-set deps → both at depth 0
    expect(result.order).toEqual(['change-a', 'change-b']);
  });

  it('handles a complex multi-level DAG', () => {
    const changes = map({
      'db-setup': {},
      'auth-module': { dependsOn: ['db-setup'] },
      'api-v2': { dependsOn: ['db-setup'] },
      'user-routes': { dependsOn: ['auth-module', 'api-v2'] },
      'admin-panel': { dependsOn: ['auth-module'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(false);
    expect(result.order).toEqual([
      'db-setup',
      'api-v2',
      'auth-module',
      'admin-panel',
      'user-routes',
    ]);
  });

  it('handles self-dependency as a cycle', () => {
    const changes = map({
      'self-loop': { dependsOn: ['self-loop'] },
    });
    const result = topologicalSort(changes);
    expect(result.cycleDetected).toBe(true);
    expect(result.order).toEqual([]);
  });

  it('produces deterministic results across multiple invocations', () => {
    const changes = map({
      'z': {},
      'a': {},
      'm': { dependsOn: ['a'] },
      'b': { dependsOn: ['a'] },
    });
    const results = Array.from({ length: 10 }, () => topologicalSort(changes));
    const orders = results.map(r => r.order);
    // Every invocation should produce the same order
    for (const order of orders) {
      expect(order).toEqual(orders[0]);
    }
    expect(orders[0]).toEqual(['a', 'b', 'm', 'z']);
  });
});
