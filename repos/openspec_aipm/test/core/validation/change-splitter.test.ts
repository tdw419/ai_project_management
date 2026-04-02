import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { promises as fs } from 'fs';
import path from 'path';
import os from 'os';
import {
  splitChange,
  findChildren,
  generateChildIds,
  type SplitOptions,
} from '../../../src/core/validation/change-splitter.js';
import { readChangeMetadata } from '../../../src/utils/change-metadata.js';

describe('change-splitter', () => {
  let tempRoot: string;
  let changesPath: string;
  let originalCwd: string;

  beforeEach(async () => {
    originalCwd = process.cwd();
    tempRoot = path.join(os.tmpdir(), `openspec-split-test-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`);
    changesPath = path.join(tempRoot, 'openspec', 'changes');
    await fs.mkdir(changesPath, { recursive: true });
    process.chdir(tempRoot);
  });

  afterEach(async () => {
    process.chdir(originalCwd);
    await fs.rm(tempRoot, { recursive: true, force: true });
  });

  /**
   * Helper: create a minimal change directory.
   */
  async function createChange(id: string, proposalContent?: string): Promise<string> {
    const dir = path.join(changesPath, id);
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(
      path.join(dir, 'proposal.md'),
      proposalContent ?? `# Change: ${id}\n\n## Why\nTesting.\n\n## What Changes\n- Something`,
      'utf-8',
    );
    return dir;
  }

  describe('generateChildIds', () => {
    it('should generate default 2 slices when no options', () => {
      const ids = generateChildIds('big-change', {});
      expect(ids).toEqual(['big-change-slice-1', 'big-change-slice-2']);
    });

    it('should generate N slices when slices option provided', () => {
      const ids = generateChildIds('big-change', { slices: 4 });
      expect(ids).toEqual([
        'big-change-slice-1',
        'big-change-slice-2',
        'big-change-slice-3',
        'big-change-slice-4',
      ]);
    });

    it('should use explicit names when provided', () => {
      const ids = generateChildIds('big-change', { names: ['auth', 'db', 'api'] });
      expect(ids).toEqual(['big-change-auth', 'big-change-db', 'big-change-api']);
    });

    it('should produce same output for same inputs (deterministic)', () => {
      const ids1 = generateChildIds('my-change', { slices: 3 });
      const ids2 = generateChildIds('my-change', { slices: 3 });
      expect(ids1).toEqual(ids2);
    });

    it('should enforce minimum of 2 slices', () => {
      const ids = generateChildIds('x', { slices: 1 });
      expect(ids).toHaveLength(2);
    });

    it('should handle slices=0 as default 2', () => {
      const ids = generateChildIds('x', { slices: 0 });
      expect(ids).toHaveLength(2);
    });
  });

  describe('findChildren', () => {
    it('should return empty array when no children exist', async () => {
      await createChange('parent-change');
      const children = await findChildren(changesPath, 'parent-change');
      expect(children).toEqual([]);
    });

    it('should find children by parent metadata', async () => {
      await createChange('parent-change');
      const childDir = path.join(changesPath, 'child-a');
      await fs.mkdir(childDir, { recursive: true });
      await fs.writeFile(
        path.join(childDir, '.openspec.yaml'),
        'schema: spec-driven\nparent: parent-change\ndependsOn:\n  - parent-change\n',
        'utf-8',
      );
      await fs.writeFile(path.join(childDir, 'proposal.md'), '# Child A', 'utf-8');

      const children = await findChildren(changesPath, 'parent-change');
      expect(children).toEqual(['child-a']);
    });

    it('should find multiple children sorted lexicographically', async () => {
      await createChange('parent-change');

      for (const name of ['child-z', 'child-a', 'child-m']) {
        const childDir = path.join(changesPath, name);
        await fs.mkdir(childDir, { recursive: true });
        await fs.writeFile(
          path.join(childDir, '.openspec.yaml'),
          `schema: spec-driven\nparent: parent-change\ndependsOn:\n  - parent-change\n`,
          'utf-8',
        );
        await fs.writeFile(path.join(childDir, 'proposal.md'), `# ${name}`, 'utf-8');
      }

      const children = await findChildren(changesPath, 'parent-change');
      expect(children).toEqual(['child-a', 'child-m', 'child-z']);
    });

    it('should ignore changes without metadata', async () => {
      await createChange('parent-change');
      const orphanDir = path.join(changesPath, 'orphan-change');
      await fs.mkdir(orphanDir, { recursive: true });
      await fs.writeFile(path.join(orphanDir, 'proposal.md'), '# Orphan', 'utf-8');

      const children = await findChildren(changesPath, 'parent-change');
      expect(children).toEqual([]);
    });
  });

  describe('splitChange', () => {
    it('should error when source change does not exist', async () => {
      const result = await splitChange(changesPath, {
        changeId: 'nonexistent',
        overwrite: false,
      });
      expect(result.error).toBeTruthy();
      expect(result.error).toContain('not found');
      expect(result.parentConverted).toBe(false);
      expect(result.children).toEqual([]);
    });

    it('should create default 2 child slices', async () => {
      await createChange('big-feature');

      const result = await splitChange(changesPath, {
        changeId: 'big-feature',
        overwrite: false,
      });

      expect(result.error).toBeUndefined();
      expect(result.parentConverted).toBe(true);
      expect(result.children).toHaveLength(2);
      expect(result.children.map(c => c.id)).toEqual([
        'big-feature-slice-1',
        'big-feature-slice-2',
      ]);
    });

    it('should create children with correct metadata (parent + dependsOn)', async () => {
      await createChange('my-change');

      const result = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });

      for (const child of result.children) {
        expect(child.metadata.parent).toBe('my-change');
        expect(child.metadata.dependsOn).toEqual(['my-change']);
        expect(child.metadata.schema).toBe('spec-driven');
      }
    });

    it('should create proposal.md stub in each child', async () => {
      await createChange('my-change');

      const result = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });

      for (const child of result.children) {
        const proposalPath = path.join(child.dir, 'proposal.md');
        const content = await fs.readFile(proposalPath, 'utf-8');
        expect(content).toContain('# Proposal:');
        expect(content).toContain('my-change');
        expect(content).toContain('Dependencies');
      }
    });

    it('should create tasks.md stub in each child', async () => {
      await createChange('my-change');

      const result = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });

      for (const child of result.children) {
        const tasksPath = path.join(child.dir, 'tasks.md');
        const content = await fs.readFile(tasksPath, 'utf-8');
        expect(content).toContain('# Tasks:');
        expect(content).toContain('- [ ]');
      }
    });

    it('should create .openspec.yaml in each child', async () => {
      await createChange('my-change');

      const result = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });

      for (const child of result.children) {
        const metadata = readChangeMetadata(child.dir);
        expect(metadata).toBeTruthy();
        expect(metadata!.parent).toBe('my-change');
        expect(metadata!.dependsOn).toEqual(['my-change']);
      }
    });

    it('should convert source into parent planning container', async () => {
      await createChange('my-change');

      await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });

      const proposal = await fs.readFile(
        path.join(changesPath, 'my-change', 'proposal.md'),
        'utf-8',
      );
      expect(proposal).toContain('Split Status');
      expect(proposal).toContain('planning container');
    });

    it('should respect custom slice count', async () => {
      await createChange('big-change');

      const result = await splitChange(changesPath, {
        changeId: 'big-change',
        slices: 3,
        overwrite: false,
      });

      expect(result.children).toHaveLength(3);
      expect(result.children.map(c => c.id)).toEqual([
        'big-change-slice-1',
        'big-change-slice-2',
        'big-change-slice-3',
      ]);
    });

    it('should respect custom names', async () => {
      await createChange('big-change');

      const result = await splitChange(changesPath, {
        changeId: 'big-change',
        names: ['auth', 'storage', 'ui'],
        overwrite: false,
      });

      expect(result.children).toHaveLength(3);
      expect(result.children.map(c => c.id)).toEqual([
        'big-change-auth',
        'big-change-storage',
        'big-change-ui',
      ]);
    });

    it('should inherit schema from source metadata', async () => {
      const dir = await createChange('schema-change');
      await fs.writeFile(
        path.join(dir, '.openspec.yaml'),
        'schema: spec-driven\n',
        'utf-8',
      );

      const result = await splitChange(changesPath, {
        changeId: 'schema-change',
        overwrite: false,
      });

      for (const child of result.children) {
        expect(child.metadata.schema).toBe('spec-driven');
      }
    });
  });

  describe('re-split protection (deterministic error without overwrite)', () => {
    it('should error on re-split without overwrite flag', async () => {
      await createChange('my-change');

      // First split succeeds
      const result1 = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });
      expect(result1.error).toBeUndefined();

      // Second split fails with deterministic error
      const result2 = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });
      expect(result2.error).toBeTruthy();
      expect(result2.error).toContain('already been split');
      expect(result2.error).toContain('--overwrite');
      expect(result2.parentConverted).toBe(false);
      expect(result2.children).toEqual([]);
    });

    it('should produce same error message for repeated re-split attempts (deterministic)', async () => {
      await createChange('my-change');

      await splitChange(changesPath, { changeId: 'my-change', overwrite: false });

      const result2 = await splitChange(changesPath, { changeId: 'my-change', overwrite: false });
      const result3 = await splitChange(changesPath, { changeId: 'my-change', overwrite: false });

      expect(result2.error).toBe(result3.error);
    });
  });

  describe('--overwrite mode', () => {
    it('should succeed with overwrite after initial split', async () => {
      await createChange('my-change');

      // First split
      await splitChange(changesPath, {
        changeId: 'my-change',
        names: ['alpha', 'beta'],
        overwrite: false,
      });

      // Re-split with overwrite
      const result = await splitChange(changesPath, {
        changeId: 'my-change',
        names: ['gamma', 'delta'],
        overwrite: true,
      });

      expect(result.error).toBeUndefined();
      expect(result.parentConverted).toBe(true);
      expect(result.children).toHaveLength(2);
      expect(result.children.map(c => c.id)).toEqual([
        'my-change-gamma',
        'my-change-delta',
      ]);
    });

    it('should remove old children when overwriting', async () => {
      await createChange('my-change');

      // First split
      await splitChange(changesPath, {
        changeId: 'my-change',
        names: ['alpha'],
        overwrite: false,
      });

      // Verify first child exists
      const alphaDir = path.join(changesPath, 'my-change-alpha');
      await expect(fs.access(alphaDir)).resolves.toBeUndefined();

      // Re-split with different names
      await splitChange(changesPath, {
        changeId: 'my-change',
        names: ['bravo'],
        overwrite: true,
      });

      // Old child should be gone
      await expect(fs.access(alphaDir)).rejects.toThrow();

      // New child should exist
      const bravoDir = path.join(changesPath, 'my-change-bravo');
      await expect(fs.access(bravoDir)).resolves.toBeUndefined();
    });

    it('should work with --force as alias for --overwrite', async () => {
      await createChange('my-change');

      // Initial split
      await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: false,
      });

      // Re-split with force (same as overwrite)
      const result = await splitChange(changesPath, {
        changeId: 'my-change',
        overwrite: true, // CLI maps --force to overwrite: true
        slices: 3,
      });

      expect(result.error).toBeUndefined();
      expect(result.children).toHaveLength(3);
    });
  });

  describe('split output structure validation', () => {
    it('should create valid change directories that can be listed', async () => {
      await createChange('parent');

      const result = await splitChange(changesPath, {
        changeId: 'parent',
        names: ['child-a', 'child-b'],
        overwrite: false,
      });

      // Verify each child is a proper change directory
      for (const child of result.children) {
        const entries = await fs.readdir(child.dir);
        expect(entries).toContain('proposal.md');
        expect(entries).toContain('tasks.md');
        expect(entries).toContain('.openspec.yaml');
      }

      // Verify parent's proposal was updated
      const parentProposal = await fs.readFile(
        path.join(changesPath, 'parent', 'proposal.md'),
        'utf-8',
      );
      expect(parentProposal).toContain('parent-child-a');
      expect(parentProposal).toContain('parent-child-b');
    });

    it('should produce children whose metadata is valid and readable', async () => {
      await createChange('parent');

      const result = await splitChange(changesPath, {
        changeId: 'parent',
        overwrite: false,
      });

      for (const child of result.children) {
        const metadata = readChangeMetadata(child.dir);
        expect(metadata).not.toBeNull();
        expect(metadata!.schema).toBe('spec-driven');
        expect(metadata!.parent).toBe('parent');
        expect(metadata!.dependsOn).toEqual(['parent']);
      }
    });
  });
});
