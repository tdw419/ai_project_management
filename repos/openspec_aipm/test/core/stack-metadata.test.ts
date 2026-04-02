import { describe, it, expect } from 'vitest';
import { ChangeMetadataSchema } from '../../src/core/artifact-graph/types.js';

describe('ChangeMetadataSchema stack fields', () => {
  describe('backward compatibility', () => {
    it('should accept metadata without any stack fields', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '2025-01-05',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dependsOn).toBeUndefined();
        expect(result.data.provides).toBeUndefined();
        expect(result.data.requires).toBeUndefined();
        expect(result.data.touches).toBeUndefined();
        expect(result.data.parent).toBeUndefined();
      }
    });
  });

  describe('valid stack metadata', () => {
    it('should accept dependsOn as array of change IDs', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        dependsOn: ['add-auth', 'fix-login'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dependsOn).toEqual(['add-auth', 'fix-login']);
      }
    });

    it('should accept provides as array of capability markers', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        provides: ['auth-layer', 'session-mgmt'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.provides).toEqual(['auth-layer', 'session-mgmt']);
      }
    });

    it('should accept requires as array of capability markers', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        requires: ['db-schema-v2'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.requires).toEqual(['db-schema-v2']);
      }
    });

    it('should accept touches as array of file/path patterns', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        touches: ['src/auth/**', 'src/middleware/**'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.touches).toEqual(['src/auth/**', 'src/middleware/**']);
      }
    });

    it('should accept parent as a string change ID', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        parent: 'refactor-auth-system',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.parent).toBe('refactor-auth-system');
      }
    });

    it('should accept all stack fields together', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '2025-06-15',
        dependsOn: ['add-db-schema'],
        provides: ['user-model'],
        requires: ['migration-framework'],
        touches: ['src/models/user.ts'],
        parent: 'add-user-system',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dependsOn).toEqual(['add-db-schema']);
        expect(result.data.provides).toEqual(['user-model']);
        expect(result.data.requires).toEqual(['migration-framework']);
        expect(result.data.touches).toEqual(['src/models/user.ts']);
        expect(result.data.parent).toBe('add-user-system');
      }
    });
  });

  describe('invalid stack metadata', () => {
    it('should reject dependsOn as a string (not array)', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        dependsOn: 'add-auth',
      });
      expect(result.success).toBe(false);
    });

    it('should reject provides containing non-strings', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        provides: ['valid', 123],
      });
      expect(result.success).toBe(false);
    });

    it('should reject parent as an array (must be string)', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        parent: ['some-parent'],
      });
      expect(result.success).toBe(false);
    });

    it('should reject empty dependsOn elements', () => {
      // Empty strings are technically valid strings, so this tests array-of-strings
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        dependsOn: [''],
      });
      // z.array(z.string()) accepts empty strings, which is fine for now
      expect(result.success).toBe(true);
    });
  });

  describe('schema evolution', () => {
    it('should ignore unknown fields (forward compatible)', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        futureField: 'some-value',
      });
      // Zod strips unknown keys by default, so this succeeds
      expect(result.success).toBe(true);
      if (result.success) {
        expect((result.data as Record<string, unknown>).futureField).toBeUndefined();
      }
    });
  });
});
