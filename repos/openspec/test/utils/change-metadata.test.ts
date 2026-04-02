import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { promises as fs } from 'fs';
import path from 'path';
import os from 'os';
import { randomUUID } from 'crypto';
import {
  writeChangeMetadata,
  readChangeMetadata,
  resolveSchemaForChange,
  validateSchemaName,
  ChangeMetadataError,
} from '../../src/utils/change-metadata.js';
import { ChangeMetadataSchema } from '../../src/core/artifact-graph/types.js';

describe('ChangeMetadataSchema', () => {
  describe('valid metadata', () => {
    it('should accept valid schema with created date', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '2025-01-05',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.schema).toBe('spec-driven');
        expect(result.data.created).toBe('2025-01-05');
      }
    });

    it('should accept valid schema without created date', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'custom-schema',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.schema).toBe('custom-schema');
        expect(result.data.created).toBeUndefined();
      }
    });
  });

  describe('invalid metadata', () => {
    it('should reject empty schema', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: '',
      });
      expect(result.success).toBe(false);
    });

    it('should reject missing schema', () => {
      const result = ChangeMetadataSchema.safeParse({
        created: '2025-01-05',
      });
      expect(result.success).toBe(false);
    });

    it('should reject invalid date format', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '01/05/2025', // Wrong format
      });
      expect(result.success).toBe(false);
    });

    it('should reject non-ISO date format', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '2025-1-5', // Missing leading zeros
      });
      expect(result.success).toBe(false);
    });
  });
});

describe('writeChangeMetadata', () => {
  let testDir: string;
  let changeDir: string;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `openspec-test-${randomUUID()}`);
    changeDir = path.join(testDir, 'openspec', 'changes', 'test-change');
    await fs.mkdir(changeDir, { recursive: true });
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  it('should write valid YAML metadata file', async () => {
    writeChangeMetadata(changeDir, {
      schema: 'spec-driven',
      created: '2025-01-05',
    });

    const metaPath = path.join(changeDir, '.openspec.yaml');
    const content = await fs.readFile(metaPath, 'utf-8');

    expect(content).toContain('schema: spec-driven');
    expect(content).toContain('created: 2025-01-05');
  });

  it('should throw error for unknown schema', () => {
    expect(() =>
      writeChangeMetadata(changeDir, {
        schema: 'unknown-schema',
        created: '2025-01-05',
      })
    ).toThrow(/Unknown schema 'unknown-schema'/);
  });
});

describe('readChangeMetadata', () => {
  let testDir: string;
  let changeDir: string;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `openspec-test-${randomUUID()}`);
    changeDir = path.join(testDir, 'openspec', 'changes', 'test-change');
    await fs.mkdir(changeDir, { recursive: true });
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  it('should return null when no metadata file exists', () => {
    const result = readChangeMetadata(changeDir);
    expect(result).toBeNull();
  });

  it('should read valid metadata', async () => {
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(
      metaPath,
      'schema: spec-driven\ncreated: "2025-01-05"\n',
      'utf-8'
    );

    const result = readChangeMetadata(changeDir);
    expect(result).toEqual({
      schema: 'spec-driven',
      created: '2025-01-05',
    });
  });

  it('should throw ChangeMetadataError for invalid YAML', async () => {
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, '{ invalid yaml', 'utf-8');

    expect(() => readChangeMetadata(changeDir)).toThrow(ChangeMetadataError);
  });

  it('should throw ChangeMetadataError for missing schema field', async () => {
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'created: "2025-01-05"\n', 'utf-8');

    expect(() => readChangeMetadata(changeDir)).toThrow(ChangeMetadataError);
  });

  it('should throw ChangeMetadataError for unknown schema', async () => {
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'schema: unknown-schema\n', 'utf-8');

    expect(() => readChangeMetadata(changeDir)).toThrow(/Unknown schema/);
  });
});

describe('resolveSchemaForChange', () => {
  let testDir: string;
  let changeDir: string;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `openspec-test-${randomUUID()}`);
    changeDir = path.join(testDir, 'openspec', 'changes', 'test-change');
    await fs.mkdir(changeDir, { recursive: true });
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  it('should return explicit schema when provided', async () => {
    // Even with metadata file, explicit schema wins
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'schema: spec-driven\n', 'utf-8');

    const result = resolveSchemaForChange(changeDir, 'custom-schema');
    expect(result).toBe('custom-schema');
  });

  it('should return schema from metadata when no explicit schema', async () => {
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'schema: spec-driven\n', 'utf-8');

    const result = resolveSchemaForChange(changeDir);
    expect(result).toBe('spec-driven');
  });

  it('should return default when no metadata and no explicit schema', () => {
    const result = resolveSchemaForChange(changeDir);
    expect(result).toBe('spec-driven');
  });

  it('should return default when metadata read fails', async () => {
    // Create an invalid metadata file
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, '{ invalid yaml', 'utf-8');

    // Should fall back to default, not throw
    const result = resolveSchemaForChange(changeDir);
    expect(result).toBe('spec-driven');
  });

  it('should use project config schema when no metadata exists', async () => {
    // Create project config
    const configDir = path.join(testDir, 'openspec');
    await fs.mkdir(configDir, { recursive: true });
    await fs.writeFile(
      path.join(configDir, 'config.yaml'),
      'schema: custom-schema\n',
      'utf-8'
    );

    const result = resolveSchemaForChange(changeDir);
    expect(result).toBe('custom-schema');
  });

  it('should prefer change metadata over project config', async () => {
    // Create project config
    const configDir = path.join(testDir, 'openspec');
    await fs.mkdir(configDir, { recursive: true });
    await fs.writeFile(
      path.join(configDir, 'config.yaml'),
      'schema: custom-schema\n',
      'utf-8'
    );

    // Create change metadata with different schema
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'schema: spec-driven\n', 'utf-8');

    const result = resolveSchemaForChange(changeDir);
    expect(result).toBe('spec-driven'); // Change metadata wins
  });

  it('should prefer explicit schema over all config sources', async () => {
    // Create project config
    const configDir = path.join(testDir, 'openspec');
    await fs.mkdir(configDir, { recursive: true });
    await fs.writeFile(
      path.join(configDir, 'config.yaml'),
      'schema: custom-schema\n',
      'utf-8'
    );

    // Create change metadata
    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'schema: spec-driven\n', 'utf-8');

    // Explicit schema should win
    const result = resolveSchemaForChange(changeDir, 'custom-schema');
    expect(result).toBe('custom-schema');
  });

  it('should test full precedence order: CLI > metadata > config > default', async () => {
    // Setup all levels
    const configDir = path.join(testDir, 'openspec');
    await fs.mkdir(configDir, { recursive: true });
    await fs.writeFile(
      path.join(configDir, 'config.yaml'),
      'schema: custom-schema\n',
      'utf-8'
    );

    const metaPath = path.join(changeDir, '.openspec.yaml');
    await fs.writeFile(metaPath, 'schema: spec-driven\n', 'utf-8');

    // Test each level
    expect(resolveSchemaForChange(changeDir, 'custom-schema')).toBe('custom-schema'); // CLI wins
    expect(resolveSchemaForChange(changeDir)).toBe('spec-driven'); // Metadata wins when no CLI

    // Remove metadata, config should win
    await fs.unlink(metaPath);
    expect(resolveSchemaForChange(changeDir)).toBe('custom-schema'); // Config wins

    // Remove config, default should win
    await fs.unlink(path.join(configDir, 'config.yaml'));
    expect(resolveSchemaForChange(changeDir)).toBe('spec-driven'); // Default wins
  });
});

describe('validateSchemaName', () => {
  it('should accept valid schema name', () => {
    expect(() => validateSchemaName('spec-driven')).not.toThrow();
  });

  it('should throw for unknown schema', () => {
    expect(() => validateSchemaName('unknown-schema')).toThrow(
      /Unknown schema 'unknown-schema'/
    );
  });
});

// --- Stack metadata fields (SEC-1) ---

describe('ChangeMetadataSchema stack fields', () => {
  describe('valid stack metadata', () => {
    it('should accept dependsOn with change names', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        dependsOn: ['auth-refactor', 'db-migration'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dependsOn).toEqual(['auth-refactor', 'db-migration']);
      }
    });

    it('should accept provides with capability names', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        provides: ['user-auth', 'session-management'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.provides).toEqual(['user-auth', 'session-management']);
      }
    });

    it('should accept requires with capability names', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        requires: ['database-schema', 'migration-runner'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.requires).toEqual(['database-schema', 'migration-runner']);
      }
    });

    it('should accept touches with file paths', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        touches: ['src/auth/login.ts', 'src/auth/session.ts'],
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.touches).toEqual(['src/auth/login.ts', 'src/auth/session.ts']);
      }
    });

    it('should accept parent with change name', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        parent: 'large-refactor',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.parent).toBe('large-refactor');
      }
    });

    it('should accept all stack fields together', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '2025-06-15',
        dependsOn: ['auth-refactor'],
        provides: ['user-session-api'],
        requires: ['database-schema'],
        touches: ['src/session.ts'],
        parent: 'auth-overhaul',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dependsOn).toEqual(['auth-refactor']);
        expect(result.data.provides).toEqual(['user-session-api']);
        expect(result.data.requires).toEqual(['database-schema']);
        expect(result.data.touches).toEqual(['src/session.ts']);
        expect(result.data.parent).toBe('auth-overhaul');
      }
    });
  });

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

    it('should accept bare minimum schema-only metadata', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'custom-schema',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.schema).toBe('custom-schema');
        expect(result.data.created).toBeUndefined();
        expect(result.data.dependsOn).toBeUndefined();
        expect(result.data.provides).toBeUndefined();
        expect(result.data.requires).toBeUndefined();
        expect(result.data.touches).toBeUndefined();
        expect(result.data.parent).toBeUndefined();
      }
    });
  });

  describe('invalid stack metadata', () => {
    it('should reject dependsOn with empty strings', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        dependsOn: ['valid', ''],
      });
      expect(result.success).toBe(false);
    });

    it('should reject provides with empty strings', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        provides: [''],
      });
      expect(result.success).toBe(false);
    });

    it('should reject requires with empty strings', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        requires: [''],
      });
      expect(result.success).toBe(false);
    });

    it('should reject touches with empty strings', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        touches: [''],
      });
      expect(result.success).toBe(false);
    });

    it('should reject empty parent string', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        parent: '',
      });
      expect(result.success).toBe(false);
    });

    it('should reject dependsOn as non-array', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        dependsOn: 'not-an-array',
      });
      expect(result.success).toBe(false);
    });

    it('should reject parent as non-string', () => {
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        parent: 42,
      });
      expect(result.success).toBe(false);
    });
  });

  describe('schema evolution', () => {
    it('should parse metadata written before stack fields existed', () => {
      // Simulates reading an old .openspec.yaml that only has schema + created
      const result = ChangeMetadataSchema.safeParse({
        schema: 'spec-driven',
        created: '2024-12-01',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        // All stack fields should be absent, not null or empty arrays
        expect(result.data).not.toHaveProperty('dependsOn');
        expect(result.data).not.toHaveProperty('provides');
        expect(result.data).not.toHaveProperty('requires');
        expect(result.data).not.toHaveProperty('touches');
        expect(result.data).not.toHaveProperty('parent');
      }
    });

    it('should round-trip metadata with stack fields through read/write', async () => {
      const testDir = path.join(os.tmpdir(), `openspec-stack-test-${randomUUID()}`);
      const changeDir = path.join(testDir, 'openspec', 'changes', 'stack-test');
      await fs.mkdir(changeDir, { recursive: true });

      try {
        const metadata = {
          schema: 'spec-driven',
          created: '2025-06-15',
          dependsOn: ['prerequisite-change'],
          provides: ['new-api'],
          requires: ['old-api'],
          touches: ['src/new-feature.ts', 'tests/new-feature.test.ts'],
          parent: 'big-feature',
        };

        writeChangeMetadata(changeDir, metadata);

        const readBack = readChangeMetadata(changeDir);
        expect(readBack).toEqual(metadata);
      } finally {
        await fs.rm(testDir, { recursive: true, force: true });
      }
    });

    it('should read old-format metadata without stack fields', async () => {
      const testDir = path.join(os.tmpdir(), `openspec-stack-old-${randomUUID()}`);
      const changeDir = path.join(testDir, 'openspec', 'changes', 'old-change');
      await fs.mkdir(changeDir, { recursive: true });

      try {
        // Write old-style metadata (no stack fields)
        const metaPath = path.join(changeDir, '.openspec.yaml');
        await fs.writeFile(
          metaPath,
          'schema: spec-driven\ncreated: "2024-12-01"\n',
          'utf-8'
        );

        const readBack = readChangeMetadata(changeDir);
        expect(readBack).toEqual({
          schema: 'spec-driven',
          created: '2024-12-01',
        });
        // Ensure no accidental stack field defaults leaked in
        expect(Object.keys(readBack!)).not.toContain('dependsOn');
        expect(Object.keys(readBack!)).not.toContain('provides');
        expect(Object.keys(readBack!)).not.toContain('requires');
        expect(Object.keys(readBack!)).not.toContain('touches');
        expect(Object.keys(readBack!)).not.toContain('parent');
      } finally {
        await fs.rm(testDir, { recursive: true, force: true });
      }
    });
  });
});
