import { describe, it, expect } from 'vitest';
import {
  topologicalSort,
  getUnblockedChanges,
} from '../../../src/core/validation/topological-sort.js';
import type { ChangeEntry } from '../../../src/core/validation/stack-validator.js';

// Helper to build ChangeEntry quickly
function entry(id: string, overrides: Partial<ChangeEntry['metadata']> = {}): ChangeEntry {
  return {
    id,
    metadata: {
      schema: 'spec-driven',
      ...overrides,
    },
  };
}

describe('topologicalSort', () => {
  describe('basic ordering', () => {
    it('should return empty nodes for empty input', () => {
      const result = topologicalSort([]);
      expect(result.nodes).toEqual([]);
      expect(result.cycleError).toBeNull();
    });

    it('should return single change at depth 0', () => {
      const result = topologicalSort([entry('change-a')]);
      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]).toEqual({
        id: 'change-a',
        depth: 0,
        dependsOn: [],
      });
    });

    it('should order linear chain correctly', () => {
      const result = topologicalSort([
        entry('change-a'),
        entry('change-b', { dependsOn: ['change-a'] }),
        entry('change-c', { dependsOn: ['change-b'] }),
      ]);
      const ids = result.nodes.map(n => n.id);
      expect(ids).toEqual(['change-a', 'change-b', 'change-c']);
      expect(result.nodes[0].depth).toBe(0);
      expect(result.nodes[1].depth).toBe(1);
      expect(result.nodes[2].depth).toBe(2);
    });

    it('should handle diamond dependency', () => {
      // A depends on B and C, B and C depend on D
      const result = topologicalSort([
        entry('change-d'),
        entry('change-b', { dependsOn: ['change-d'] }),
        entry('change-c', { dependsOn: ['change-d'] }),
        entry('change-a', { dependsOn: ['change-b', 'change-c'] }),
      ]);
      const ids = result.nodes.map(n => n.id);
      // D at depth 0, B and C at depth 1, A at depth 2
      expect(ids[0]).toBe('change-d');
      expect(ids[1]).toBe('change-b');
      expect(ids[2]).toBe('change-c');
      expect(ids[3]).toBe('change-a');
      expect(result.nodes[0].depth).toBe(0);
      expect(result.nodes[1].depth).toBe(1);
      expect(result.nodes[2].depth).toBe(1);
      expect(result.nodes[3].depth).toBe(2);
    });
  });

  describe('deterministic tie-breaking (lexicographic by ID at equal depth)', () => {
    it('should sort same-depth changes lexicographically', () => {
      const result = topologicalSort([
        entry('zebra-change'),
        entry('alpha-change'),
        entry('middle-change'),
      ]);
      const ids = result.nodes.map(n => n.id);
      expect(ids).toEqual(['alpha-change', 'middle-change', 'zebra-change']);
    });

    it('should sort lexicographically within same depth level in a complex graph', () => {
      // Root: z-base, a-base (both depth 0)
      // Child: mid-child depends on a-base (depth 1)
      // Child: a-child depends on z-base (depth 1)
      const result = topologicalSort([
        entry('z-base'),
        entry('a-base'),
        entry('mid-child', { dependsOn: ['a-base'] }),
        entry('a-child', { dependsOn: ['z-base'] }),
      ]);
      const ids = result.nodes.map(n => n.id);
      // Depth 0: a-base, z-base (lex order)
      // Depth 1: a-child, mid-child (lex order)
      expect(ids).toEqual(['a-base', 'z-base', 'a-child', 'mid-child']);
    });

    it('should produce same result regardless of input order', () => {
      const entries = [
        entry('change-c', { dependsOn: ['change-a'] }),
        entry('change-a'),
        entry('change-b', { dependsOn: ['change-a'] }),
      ];
      const result1 = topologicalSort([...entries]);
      const result2 = topologicalSort([...entries].reverse());
      const ids1 = result1.nodes.map(n => n.id);
      const ids2 = result2.nodes.map(n => n.id);
      expect(ids1).toEqual(ids2);
    });
  });

  describe('cycle detection', () => {
    it('should return cycle error for direct cycle', () => {
      const result = topologicalSort([
        entry('change-a', { dependsOn: ['change-b'] }),
        entry('change-b', { dependsOn: ['change-a'] }),
      ]);
      expect(result.cycleError).toBeTruthy();
      expect(result.cycleError).toContain('cycle');
      expect(result.nodes).toEqual([]);
    });

    it('should return cycle error for longer cycle', () => {
      const result = topologicalSort([
        entry('change-a', { dependsOn: ['change-b'] }),
        entry('change-b', { dependsOn: ['change-c'] }),
        entry('change-c', { dependsOn: ['change-a'] }),
      ]);
      expect(result.cycleError).toBeTruthy();
      expect(result.cycleError).toContain('cycle');
      expect(result.nodes).toEqual([]);
    });
  });

  describe('ignores unknown dependencies', () => {
    it('should ignore dependsOn references to changes not in the active set', () => {
      const result = topologicalSort([
        entry('change-a', { dependsOn: ['archived-change'] }),
      ]);
      // archived-change is not in the active set, so change-a has depth 0
      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0].depth).toBe(0);
      // dependsOn should only contain known deps
      expect(result.nodes[0].dependsOn).toEqual([]);
    });
  });
});

describe('getUnblockedChanges', () => {
  describe('basic behavior', () => {
    it('should return all changes when no dependencies exist', () => {
      const result = getUnblockedChanges([
        entry('change-a'),
        entry('change-b'),
        entry('change-c'),
      ]);
      expect(result.cycleError).toBeNull();
      const ids = result.nodes.map(n => n.id);
      expect(ids).toEqual(['change-a', 'change-b', 'change-c']);
    });

    it('should return only depth-0 changes when all others are blocked', () => {
      const result = getUnblockedChanges([
        entry('change-a'),
        entry('change-b', { dependsOn: ['change-a'] }),
      ]);
      // Both are "unblocked" since all deps exist in the active set
      const ids = result.nodes.map(n => n.id);
      expect(ids).toEqual(['change-a', 'change-b']);
    });

    it('should exclude changes with missing dependencies', () => {
      const result = getUnblockedChanges([
        entry('change-a', { dependsOn: ['nonexistent'] }),
        entry('change-b'),
      ]);
      const ids = result.nodes.map(n => n.id);
      expect(ids).toEqual(['change-b']);
    });

    it('should exclude transitively blocked changes', () => {
      // change-a depends on nonexistent, change-b depends on change-a
      const result = getUnblockedChanges([
        entry('change-a', { dependsOn: ['nonexistent'] }),
        entry('change-b', { dependsOn: ['change-a'] }),
      ]);
      const ids = result.nodes.map(n => n.id);
      // Both blocked: change-a has missing dep, change-b depends on blocked change-a
      expect(ids).toEqual([]);
    });
  });

  describe('deterministic ordering', () => {
    it('should order unblocked changes by depth then lexicographic ID', () => {
      const result = getUnblockedChanges([
        entry('z-base'),
        entry('a-base'),
        entry('mid-child', { dependsOn: ['a-base'] }),
        entry('a-child', { dependsOn: ['z-base'] }),
      ]);
      const ids = result.nodes.map(n => n.id);
      expect(ids).toEqual(['a-base', 'z-base', 'a-child', 'mid-child']);
    });
  });

  describe('cycle handling', () => {
    it('should return cycle error instead of results', () => {
      const result = getUnblockedChanges([
        entry('change-a', { dependsOn: ['change-b'] }),
        entry('change-b', { dependsOn: ['change-a'] }),
      ]);
      expect(result.cycleError).toBeTruthy();
      expect(result.nodes).toEqual([]);
    });
  });

  describe('edge cases', () => {
    it('should handle empty input', () => {
      const result = getUnblockedChanges([]);
      expect(result.nodes).toEqual([]);
      expect(result.cycleError).toBeNull();
    });

    it('should handle single change with no metadata', () => {
      const result = getUnblockedChanges([entry('solo-change')]);
      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0].id).toBe('solo-change');
      expect(result.nodes[0].depth).toBe(0);
    });
  });
});
