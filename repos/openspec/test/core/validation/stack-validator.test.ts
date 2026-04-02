import { describe, it, expect } from 'vitest';
import type { ChangeMetadata } from '../../../src/core/artifact-graph/types.js';
import {
  detectCycles,
  detectMissingDependencies,
  detectBlockedChanges,
  detectOverlapWarnings,
  detectUnmatchedRequires,
  validateStack,
} from '../../../src/core/validation/stack-validator.js';

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

// ─── 2.1 Cycle Detection ───

describe('detectCycles', () => {
  it('returns empty for changes with no dependencies', () => {
    const changes = map({
      'change-a': {},
      'change-b': {},
    });
    expect(detectCycles(changes)).toEqual([]);
  });

  it('returns empty for a valid linear chain', () => {
    const changes = map({
      'change-a': {},
      'change-b': { dependsOn: ['change-a'] },
      'change-c': { dependsOn: ['change-b'] },
    });
    expect(detectCycles(changes)).toEqual([]);
  });

  it('returns empty for a valid diamond', () => {
    const changes = map({
      root: {},
      left: { dependsOn: ['root'] },
      right: { dependsOn: ['root'] },
      merge: { dependsOn: ['left', 'right'] },
    });
    expect(detectCycles(changes)).toEqual([]);
  });

  it('detects a simple two-node cycle', () => {
    const changes = map({
      'change-a': { dependsOn: ['change-b'] },
      'change-b': { dependsOn: ['change-a'] },
    });
    const issues = detectCycles(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('ERROR');
    expect(issues[0].message).toContain('Dependency cycle detected');
    expect(issues[0].message).toContain('change-a');
    expect(issues[0].message).toContain('change-b');
  });

  it('detects a three-node cycle', () => {
    const changes = map({
      'change-a': { dependsOn: ['change-c'] },
      'change-b': { dependsOn: ['change-a'] },
      'change-c': { dependsOn: ['change-b'] },
    });
    const issues = detectCycles(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('ERROR');
    expect(issues[0].message).toContain('Dependency cycle detected');
  });

  it('detects self-cycle', () => {
    const changes = map({
      'change-a': { dependsOn: ['change-a'] },
    });
    const issues = detectCycles(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].message).toContain('Dependency cycle detected');
  });

  it('detects multiple independent cycles', () => {
    const changes = map({
      'a1': { dependsOn: ['a2'] },
      'a2': { dependsOn: ['a1'] },
      'b1': { dependsOn: ['b2'] },
      'b2': { dependsOn: ['b1'] },
    });
    const issues = detectCycles(changes);
    expect(issues).toHaveLength(2);
    expect(issues.every(i => i.level === 'ERROR')).toBe(true);
  });

  it('ignores dependsOn references to changes outside the set', () => {
    const changes = map({
      'change-a': { dependsOn: ['nonexistent'] },
    });
    expect(detectCycles(changes)).toEqual([]);
  });

  it('produces deterministic error ordering', () => {
    const changes = map({
      'z-change': { dependsOn: ['a-change'] },
      'a-change': { dependsOn: ['z-change'] },
    });
    const issues = detectCycles(changes);
    expect(issues).toHaveLength(1);
    // The cycle string should be sorted
    expect(issues[0].message).toMatch(/a-change.*z-change|z-change.*a-change/);
  });
});

// ─── 2.2 Missing Dependencies ───

describe('detectMissingDependencies', () => {
  it('returns empty when all dependencies resolve', () => {
    const changes = map({
      'change-a': {},
      'change-b': { dependsOn: ['change-a'] },
    });
    expect(detectMissingDependencies(changes)).toEqual([]);
  });

  it('detects a single missing dependency', () => {
    const changes = map({
      'change-a': { dependsOn: ['nonexistent'] },
    });
    const issues = detectMissingDependencies(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('ERROR');
    expect(issues[0].path).toBe('change-a/dependsOn');
    expect(issues[0].message).toContain("'change-a'");
    expect(issues[0].message).toContain("'nonexistent'");
    expect(issues[0].message).toContain('does not exist');
  });

  it('detects multiple missing dependencies for one change', () => {
    const changes = map({
      'change-a': { dependsOn: ['missing-1', 'missing-2'] },
    });
    const issues = detectMissingDependencies(changes);
    expect(issues).toHaveLength(2);
  });

  it('detects missing dependencies across multiple changes', () => {
    const changes = map({
      'change-a': { dependsOn: ['ghost-1'] },
      'change-b': { dependsOn: ['ghost-2'] },
    });
    const issues = detectMissingDependencies(changes);
    expect(issues).toHaveLength(2);
    // Should be sorted by change name
    expect(issues[0].path).toBe('change-a/dependsOn');
    expect(issues[1].path).toBe('change-b/dependsOn');
  });

  it('returns empty when no change has dependsOn', () => {
    const changes = map({
      'change-a': {},
      'change-b': {},
    });
    expect(detectMissingDependencies(changes)).toEqual([]);
  });

  it('mixes resolved and missing deps correctly', () => {
    const changes = map({
      'change-a': {},
      'change-b': { dependsOn: ['change-a', 'ghost'] },
    });
    const issues = detectMissingDependencies(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].message).toContain("'ghost'");
  });
});

// ─── 2.2 Transitive Blocking ───

describe('detectBlockedChanges', () => {
  it('returns empty when there are no errors', () => {
    const changes = map({
      'change-a': {},
      'change-b': { dependsOn: ['change-a'] },
    });
    expect(detectBlockedChanges(changes, [])).toEqual([]);
  });

  it('detects change blocked by a missing dependency', () => {
    const changes = map({
      'change-a': { dependsOn: ['ghost'] },
      'change-b': { dependsOn: ['change-a'] },
    });
    const missingErrors = detectMissingDependencies(changes);
    const issues = detectBlockedChanges(changes, missingErrors);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('ERROR');
    expect(issues[0].message).toContain("'change-b'");
    expect(issues[0].message).toContain('transitively blocked');
  });

  it('detects deeply transitive blocking', () => {
    const changes = map({
      'change-a': { dependsOn: ['ghost'] },
      'change-b': { dependsOn: ['change-a'] },
      'change-c': { dependsOn: ['change-b'] },
    });
    const missingErrors = detectMissingDependencies(changes);
    const issues = detectBlockedChanges(changes, missingErrors);
    // change-b and change-c should both be blocked
    expect(issues.length).toBeGreaterThanOrEqual(2);
    const blockedNames = issues.map(i => {
      const m = i.message.match(/Change '([^']+)'/);
      return m ? m[1] : '';
    });
    expect(blockedNames).toContain('change-b');
    expect(blockedNames).toContain('change-c');
  });

  it('detects changes blocked by cyclic dependencies', () => {
    const changes = map({
      'a': { dependsOn: ['b'] },
      'b': { dependsOn: ['a'] },
      'c': { dependsOn: ['a'] },
    });
    const cycleErrors = detectCycles(changes);
    const issues = detectBlockedChanges(changes, cycleErrors);
    // 'c' depends on 'a' which is in a cycle → blocked
    expect(issues).toHaveLength(1);
    expect(issues[0].message).toContain("'c'");
    expect(issues[0].message).toContain('transitively blocked');
  });

  it('does not double-report changes that are already directly errored', () => {
    const changes = map({
      'change-a': { dependsOn: ['ghost'] },
    });
    const missingErrors = detectMissingDependencies(changes);
    const issues = detectBlockedChanges(changes, missingErrors);
    // change-a already has a direct missing dep error; should not be reported as blocked
    expect(issues).toEqual([]);
  });
});

// ─── 2.3 Overlap Warnings ───

describe('detectOverlapWarnings', () => {
  it('returns empty when no changes overlap', () => {
    const changes = map({
      'change-a': { touches: ['src/a.ts'] },
      'change-b': { touches: ['src/b.ts'] },
    });
    expect(detectOverlapWarnings(changes)).toEqual([]);
  });

  it('warns about shared touches paths', () => {
    const changes = map({
      'change-a': { touches: ['src/auth.ts', 'src/shared.ts'] },
      'change-b': { touches: ['src/shared.ts', 'src/other.ts'] },
    });
    const issues = detectOverlapWarnings(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('WARNING');
    expect(issues[0].message).toContain('src/shared.ts');
    expect(issues[0].message).toContain("'change-a'");
    expect(issues[0].message).toContain("'change-b'");
  });

  it('warns about shared provides capabilities', () => {
    const changes = map({
      'change-a': { provides: ['user-auth', 'session-api'] },
      'change-b': { provides: ['session-api'] },
    });
    const issues = detectOverlapWarnings(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('WARNING');
    expect(issues[0].message).toContain('session-api');
  });

  it('detects both touches and provides overlaps between same pair', () => {
    const changes = map({
      'change-a': { touches: ['src/x.ts'], provides: ['cap-a'] },
      'change-b': { touches: ['src/x.ts'], provides: ['cap-a'] },
    });
    const issues = detectOverlapWarnings(changes);
    expect(issues).toHaveLength(2); // one for touches, one for provides
  });

  it('handles changes without touches or provides', () => {
    const changes = map({
      'change-a': {},
      'change-b': { touches: ['src/b.ts'] },
      'change-c': { provides: ['cap-c'] },
    });
    expect(detectOverlapWarnings(changes)).toEqual([]);
  });

  it('handles multiple overlapping files', () => {
    const changes = map({
      'change-a': { touches: ['src/x.ts', 'src/y.ts', 'src/z.ts'] },
      'change-b': { touches: ['src/y.ts', 'src/z.ts'] },
    });
    const issues = detectOverlapWarnings(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].message).toContain('src/y.ts');
    expect(issues[0].message).toContain('src/z.ts');
  });
});

// ─── 2.4 Unmatched Requires ───

describe('detectUnmatchedRequires', () => {
  it('returns empty when all requires are provided', () => {
    const changes = map({
      'change-a': { provides: ['database-schema'] },
      'change-b': { requires: ['database-schema'] },
    });
    expect(detectUnmatchedRequires(changes)).toEqual([]);
  });

  it('warns about unmatched requires with no provider', () => {
    const changes = map({
      'change-a': { requires: ['missing-capability'] },
    });
    const issues = detectUnmatchedRequires(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].level).toBe('WARNING');
    expect(issues[0].message).toContain("'change-a'");
    expect(issues[0].message).toContain("'missing-capability'");
    expect(issues[0].message).toContain('no active change provides it');
  });

  it('allows a change to satisfy its own requires if it also provides', () => {
    const changes = map({
      'change-a': {
        requires: ['self-contained'],
        provides: ['self-contained'],
      },
    });
    expect(detectUnmatchedRequires(changes)).toEqual([]);
  });

  it('detects multiple unmatched requires', () => {
    const changes = map({
      'change-a': { requires: ['cap-x', 'cap-y'] },
      'change-b': { provides: ['cap-x'] },
    });
    const issues = detectUnmatchedRequires(changes);
    expect(issues).toHaveLength(1);
    expect(issues[0].message).toContain("'cap-y'");
  });

  it('handles empty change set', () => {
    expect(detectUnmatchedRequires({})).toEqual([]);
  });

  it('handles changes without requires field', () => {
    const changes = map({
      'change-a': {},
    });
    expect(detectUnmatchedRequires(changes)).toEqual([]);
  });
});

// ─── 2.5 validateStack (integration) ───

describe('validateStack', () => {
  it('returns valid for a clean change set', () => {
    const changes = map({
      'change-a': { provides: ['db'] },
      'change-b': { dependsOn: ['change-a'], requires: ['db'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(true);
    expect(result.issues).toEqual([]);
  });

  it('returns invalid when cycles exist', () => {
    const changes = map({
      'a': { dependsOn: ['b'] },
      'b': { dependsOn: ['a'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(false);
    expect(result.issues.some(i => i.level === 'ERROR')).toBe(true);
    expect(result.issues.some(i => i.message.includes('Dependency cycle'))).toBe(true);
  });

  it('returns invalid when missing deps exist', () => {
    const changes = map({
      'change-a': { dependsOn: ['ghost'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(false);
    expect(result.issues.some(i => i.message.includes('does not exist'))).toBe(true);
  });

  it('returns invalid with transitively blocked changes', () => {
    const changes = map({
      'a': { dependsOn: ['ghost'] },
      'b': { dependsOn: ['a'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(false);
    const blocked = result.issues.filter(i => i.message.includes('transitively blocked'));
    expect(blocked.length).toBeGreaterThanOrEqual(1);
  });

  it('includes overlap warnings alongside errors', () => {
    const changes = map({
      'a': { touches: ['src/x.ts'] },
      'b': { touches: ['src/x.ts'], dependsOn: ['ghost'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(false);
    const warnings = result.issues.filter(i => i.level === 'WARNING');
    expect(warnings.some(w => w.message.includes('src/x.ts'))).toBe(true);
  });

  it('includes unmatched requires warnings alongside errors', () => {
    const changes = map({
      'a': { requires: ['no-provider'], dependsOn: ['ghost'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(false);
    const warnings = result.issues.filter(i => i.level === 'WARNING');
    expect(warnings.some(w => w.message.includes('no-provider'))).toBe(true);
  });

  it('handles empty change set', () => {
    const result = validateStack({});
    expect(result.valid).toBe(true);
    expect(result.issues).toEqual([]);
  });

  it('handles single change with no metadata fields', () => {
    const changes = map({
      'solo-change': {},
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(true);
    expect(result.issues).toEqual([]);
  });

  it('validates a realistic multi-change scenario', () => {
    const changes = map({
      'db-migration': {
        provides: ['database-schema', 'migration-runner'],
        touches: ['src/db/schema.ts', 'src/db/migrator.ts'],
      },
      'auth-refactor': {
        dependsOn: ['db-migration'],
        requires: ['database-schema'],
        provides: ['user-auth'],
        touches: ['src/auth/login.ts'],
      },
      'session-api': {
        dependsOn: ['auth-refactor'],
        requires: ['user-auth'],
        provides: ['session-management'],
        touches: ['src/auth/session.ts'],
      },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(true);
    expect(result.issues).toEqual([]);
  });

  it('catches multiple issues in a complex scenario', () => {
    const changes = map({
      'a': { dependsOn: ['b'], touches: ['src/x.ts'] },
      'b': { dependsOn: ['a'], touches: ['src/x.ts'] },
      'c': { dependsOn: ['d'], requires: ['no-provider'] },
    });
    const result = validateStack(changes);
    expect(result.valid).toBe(false);

    const errors = result.issues.filter(i => i.level === 'ERROR');
    const warnings = result.issues.filter(i => i.level === 'WARNING');

    // Cycle (a↔b), missing dep (c→d), blocked (c via d)
    expect(errors.length).toBeGreaterThanOrEqual(2);
    // Overlap (a/b touch src/x.ts), unmatched requires (c needs no-provider)
    expect(warnings.length).toBeGreaterThanOrEqual(2);
  });
});
