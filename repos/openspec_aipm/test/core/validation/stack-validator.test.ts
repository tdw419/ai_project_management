import { describe, it, expect } from 'vitest';
import {
  validateChangeStack,
  type ChangeEntry,
} from '../../../src/core/validation/stack-validator.js';

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

describe('StackValidator', () => {
  describe('2.1 Dependency cycle detection', () => {
    it('should report no errors for changes with no dependencies', () => {
      const result = validateChangeStack([
        entry('change-a'),
        entry('change-b'),
      ]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should report no errors for a valid linear dependency chain', () => {
      const result = validateChangeStack([
        entry('change-a'),
        entry('change-b', { dependsOn: ['change-a'] }),
        entry('change-c', { dependsOn: ['change-b'] }),
      ]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should detect a direct cycle (A -> B -> A)', () => {
      const result = validateChangeStack([
        entry('change-a', { dependsOn: ['change-b'] }),
        entry('change-b', { dependsOn: ['change-a'] }),
      ]);
      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.errors.some(e => e.message.includes('cycle'))).toBe(true);
      // Check that the cycle path includes both changes
      const cycleError = result.errors.find(e => e.message.includes('cycle'));
      expect(cycleError!.message).toMatch(/change-a.*change-b|change-b.*change-a/);
    });

    it('should detect a longer cycle (A -> B -> C -> A)', () => {
      const result = validateChangeStack([
        entry('change-a', { dependsOn: ['change-b'] }),
        entry('change-b', { dependsOn: ['change-c'] }),
        entry('change-c', { dependsOn: ['change-a'] }),
      ]);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.message.includes('cycle'))).toBe(true);
    });

    it('should detect self-referential dependency', () => {
      const result = validateChangeStack([
        entry('change-a', { dependsOn: ['change-a'] }),
      ]);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.message.includes('Missing dependency') || e.message.includes('cycle'))).toBe(true);
    });

    it('should report cycle deterministically (sorted entry order)', () => {
      const result = validateChangeStack([
        entry('change-b', { dependsOn: ['change-a'] }),
        entry('change-a', { dependsOn: ['change-b'] }),
      ]);
      expect(result.valid).toBe(false);
      // Only one cycle error expected (not duplicated)
      const cycleErrors = result.errors.filter(e => e.message.includes('cycle'));
      expect(cycleErrors.length).toBe(1);
    });
  });

  describe('2.2 Missing dependency and transitive blocking', () => {
    it('should detect missing dependsOn target', () => {
      const result = validateChangeStack([
        entry('change-a', { dependsOn: ['nonexistent-change'] }),
      ]);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e =>
        e.message.includes('Missing dependency') && e.message.includes('nonexistent-change')
      )).toBe(true);
    });

    it('should detect multiple missing dependsOn targets', () => {
      const result = validateChangeStack([
        entry('change-a', { dependsOn: ['missing-1', 'missing-2'] }),
      ]);
      expect(result.valid).toBe(false);
      const missingErrors = result.errors.filter(e => e.message.includes('Missing dependency'));
      expect(missingErrors.length).toBe(2);
    });

    it('should report transitive blocking when upstream dep is missing', () => {
      // change-a depends on change-b, change-b depends on nonexistent
      const result = validateChangeStack([
        entry('change-b', { dependsOn: ['nonexistent'] }),
        entry('change-a', { dependsOn: ['change-b'] }),
      ]);
      expect(result.valid).toBe(false);
      // change-b should have a direct missing dep error
      expect(result.errors.some(e =>
        e.path === 'change-b' && e.message.includes('Missing dependency')
      )).toBe(true);
      // change-a should be transitively blocked
      expect(result.errors.some(e =>
        e.path === 'change-a' && e.message.includes('transitively blocked')
      )).toBe(true);
    });

    it('should handle diamond dependency without errors', () => {
      // A depends on B and C, B and C depend on D
      const result = validateChangeStack([
        entry('change-d'),
        entry('change-b', { dependsOn: ['change-d'] }),
        entry('change-c', { dependsOn: ['change-d'] }),
        entry('change-a', { dependsOn: ['change-b', 'change-c'] }),
      ]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });
  });

  describe('2.3 Overlap warnings for touches', () => {
    it('should warn when two changes touch the same area', () => {
      const result = validateChangeStack([
        entry('change-a', { touches: ['src/auth/**'] }),
        entry('change-b', { touches: ['src/auth/**'] }),
      ]);
      expect(result.warnings.some(w =>
        w.message.includes('Overlap') && w.message.includes('src/auth/**')
      )).toBe(true);
      // Warnings don't make the result invalid
      expect(result.valid).toBe(true);
    });

    it('should not warn when changes touch different areas', () => {
      const result = validateChangeStack([
        entry('change-a', { touches: ['src/auth/**'] }),
        entry('change-b', { touches: ['src/db/**'] }),
      ]);
      expect(result.warnings).toHaveLength(0);
    });

    it('should not warn when only one change has touches', () => {
      const result = validateChangeStack([
        entry('change-a', { touches: ['src/auth/**'] }),
        entry('change-b'),
      ]);
      expect(result.warnings).toHaveLength(0);
    });

    it('should handle multiple overlap areas', () => {
      const result = validateChangeStack([
        entry('change-a', { touches: ['src/auth/**', 'src/api/**'] }),
        entry('change-b', { touches: ['src/auth/**', 'src/api/**'] }),
      ]);
      const overlapWarnings = result.warnings.filter(w => w.message.includes('Overlap'));
      expect(overlapWarnings.length).toBe(2);
    });

    it('should produce deterministic output (sorted change IDs)', () => {
      const result = validateChangeStack([
        entry('change-z', { touches: ['area-1'] }),
        entry('change-a', { touches: ['area-1'] }),
      ]);
      const overlapWarn = result.warnings.find(w => w.message.includes('Overlap'));
      expect(overlapWarn).toBeDefined();
      // change-a should appear before change-z in the message
      const msg = overlapWarn!.message;
      const idxA = msg.indexOf('change-a');
      const idxZ = msg.indexOf('change-z');
      expect(idxA).toBeLessThan(idxZ);
    });
  });

  describe('2.4 Unmatched requires warnings', () => {
    it('should warn when requires has no matching provides', () => {
      const result = validateChangeStack([
        entry('change-a', { requires: ['auth-layer'] }),
      ]);
      expect(result.warnings.some(w =>
        w.message.includes('Unmatched requires') && w.message.includes('auth-layer')
      )).toBe(true);
      expect(result.valid).toBe(true);
    });

    it('should not warn when requires matches a provides', () => {
      const result = validateChangeStack([
        entry('change-a', { provides: ['auth-layer'] }),
        entry('change-b', { requires: ['auth-layer'] }),
      ]);
      const unmatchedWarnings = result.warnings.filter(w =>
        w.message.includes('Unmatched requires')
      );
      expect(unmatchedWarnings).toHaveLength(0);
    });

    it('should warn for each unmatched requires marker', () => {
      const result = validateChangeStack([
        entry('change-a', { requires: ['missing-1', 'missing-2'] }),
      ]);
      const unmatchedWarnings = result.warnings.filter(w =>
        w.message.includes('Unmatched requires')
      );
      expect(unmatchedWarnings).toHaveLength(2);
    });

    it('should consider provides from the same change as matching', () => {
      const result = validateChangeStack([
        entry('change-a', {
          provides: ['my-capability'],
          requires: ['my-capability'],
        }),
      ]);
      const unmatchedWarnings = result.warnings.filter(w =>
        w.message.includes('Unmatched requires')
      );
      expect(unmatchedWarnings).toHaveLength(0);
    });
  });

  describe('2.5 Combined scenarios', () => {
    it('should report both errors and warnings independently', () => {
      const result = validateChangeStack([
        entry('change-a', {
          touches: ['src/core/**'],
          requires: ['unprovided-cap'],
        }),
        entry('change-b', {
          dependsOn: ['nonexistent'],
          touches: ['src/core/**'],
        }),
      ]);
      expect(result.valid).toBe(false);
      // Should have error for missing dep
      expect(result.errors.some(e => e.message.includes('Missing dependency'))).toBe(true);
      // Should have warning for overlap
      expect(result.warnings.some(w => w.message.includes('Overlap'))).toBe(true);
      // Should have warning for unmatched requires
      expect(result.warnings.some(w => w.message.includes('Unmatched requires'))).toBe(true);
    });

    it('should handle empty change set', () => {
      const result = validateChangeStack([]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.warnings).toHaveLength(0);
    });

    it('should handle changes with no stack metadata at all', () => {
      const result = validateChangeStack([
        entry('change-a'),
        entry('change-b'),
        entry('change-c'),
      ]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.warnings).toHaveLength(0);
    });

    it('should handle a complex realistic scenario', () => {
      const result = validateChangeStack([
        entry('add-db-schema', {
          provides: ['db-schema-v2'],
          touches: ['src/db/**'],
        }),
        entry('add-user-model', {
          dependsOn: ['add-db-schema'],
          requires: ['db-schema-v2'],
          provides: ['user-model'],
          touches: ['src/models/**'],
        }),
        entry('add-user-api', {
          dependsOn: ['add-user-model'],
          requires: ['user-model'],
          touches: ['src/api/**'],
        }),
      ]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });
  });
});
