import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { promises as fs } from 'fs';
import path from 'path';
import { splitChange } from '../../src/core/split.js';
import { writeChangeMetadata } from '../../src/utils/change-metadata.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let tmpDir: string;

async function makeTmpProject(): Promise<string> {
  tmpDir = path.join(process.env.TMPDIR || '/tmp', `split-test-${Date.now()}`);
  const changesDir = path.join(tmpDir, 'openspec', 'changes');
  await fs.mkdir(changesDir, { recursive: true });
  return tmpDir;
}

async function cleanup(): Promise<void> {
  if (tmpDir) {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
}

async function makeChange(projectRoot: string, id: string, extra?: { schema?: string }): Promise<void> {
  const dir = path.join(projectRoot, 'openspec', 'changes', id);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(
    path.join(dir, 'proposal.md'),
    `## Why\n\nTest change.\n\n## What Changes\n\n- Something`,
    'utf-8',
  );
  writeChangeMetadata(dir, {
    schema: extra?.schema ?? 'spec-driven',
    created: '2026-01-01',
  }, projectRoot);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('splitChange', () => {
  beforeEach(async () => {
    await makeTmpProject();
  });

  afterEach(async () => {
    await cleanup();
  });

  // --- 4.1 & 4.2: Split scaffolds child slices with proper structure ---

  it('creates child directories with proposal.md, tasks.md, and .openspec.yaml', async () => {
    await makeChange(tmpDir, 'parent-change');
    const result = await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'child-a' }, { id: 'child-b' }],
    });

    expect(result.childIds).toEqual(['child-a', 'child-b']);

    for (const childId of ['child-a', 'child-b']) {
      const childDir = path.join(tmpDir, 'openspec', 'changes', childId);
      // proposal.md exists
      const proposal = await fs.readFile(path.join(childDir, 'proposal.md'), 'utf-8');
      expect(proposal).toContain('Slice of "parent-change"');
      expect(proposal).toContain('## Why');
      expect(proposal).toContain('## What Changes');

      // tasks.md exists
      const tasks = await fs.readFile(path.join(childDir, 'tasks.md'), 'utf-8');
      expect(tasks).toContain('## Tasks');

      // .openspec.yaml with parent ref
      const meta = await fs.readFile(path.join(childDir, '.openspec.yaml'), 'utf-8');
      expect(meta).toContain('parent: parent-change');
      expect(meta).toContain('schema: spec-driven');
    }
  });

  // --- 4.2: Children include parent/dependency metadata ---

  it('sets parent field in child metadata', async () => {
    await makeChange(tmpDir, 'parent-change');
    await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'child-x' }],
    });

    const metaContent = await fs.readFile(
      path.join(tmpDir, 'openspec', 'changes', 'child-x', '.openspec.yaml'),
      'utf-8',
    );
    expect(metaContent).toContain('parent: parent-change');
  });

  it('inherits schema from parent', async () => {
    await makeChange(tmpDir, 'parent-change', { schema: 'spec-driven' });
    await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'child-y' }],
    });

    const metaContent = await fs.readFile(
      path.join(tmpDir, 'openspec', 'changes', 'child-y', '.openspec.yaml'),
      'utf-8',
    );
    expect(metaContent).toContain('schema: spec-driven');
  });

  // --- 4.3: Source change becomes parent planning container ---

  it('marks parent as planning container with _splitChildren', async () => {
    await makeChange(tmpDir, 'parent-change');
    await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'part-a' }, { id: 'part-b' }],
    });

    const parentMeta = await fs.readFile(
      path.join(tmpDir, 'openspec', 'changes', 'parent-change', '.openspec.yaml'),
      'utf-8',
    );
    expect(parentMeta).toContain('_splitChildren');
    expect(parentMeta).toContain('part-a');
    expect(parentMeta).toContain('part-b');
  });

  // --- 4.4: Deterministic re-split error when no overwrite ---

  it('errors on re-split without --overwrite', async () => {
    await makeChange(tmpDir, 'parent-change');
    await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'first-slice' }],
    });

    await expect(
      splitChange(tmpDir, 'parent-change', {
        slices: [{ id: 'second-slice' }],
      }),
    ).rejects.toThrow('already been split');
  });

  it('errors when source change does not exist', async () => {
    await expect(
      splitChange(tmpDir, 'nonexistent', {
        slices: [{ id: 'child' }],
      }),
    ).rejects.toThrow('not found');
  });

  it('errors when child ID collides with existing change (no overwrite)', async () => {
    await makeChange(tmpDir, 'parent-change');
    await makeChange(tmpDir, 'already-exists');

    await expect(
      splitChange(tmpDir, 'parent-change', {
        slices: [{ id: 'already-exists' }],
      }),
    ).rejects.toThrow('already exists');
  });

  // --- 4.5: Overwrite mode ---

  it('allows re-split with overwrite=true', async () => {
    await makeChange(tmpDir, 'parent-change');
    await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'old-slice' }],
    });

    const result = await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'new-slice' }],
      overwrite: true,
    });

    expect(result.childIds).toEqual(['new-slice']);

    // old-slice should be gone
    await expect(
      fs.stat(path.join(tmpDir, 'openspec', 'changes', 'old-slice')),
    ).rejects.toThrow();

    // new-slice should exist
    const proposal = await fs.readFile(
      path.join(tmpDir, 'openspec', 'changes', 'new-slice', 'proposal.md'),
      'utf-8',
    );
    expect(proposal).toContain('Slice of "parent-change"');
  });

  it('overwrite replaces existing child directory contents', async () => {
    await makeChange(tmpDir, 'parent-change');
    await makeChange(tmpDir, 'existing-child');

    // Split with overwrite should replace existing-child
    const result = await splitChange(tmpDir, 'parent-change', {
      slices: [{ id: 'existing-child' }],
      overwrite: true,
    });

    expect(result.childIds).toEqual(['existing-child']);
    const meta = await fs.readFile(
      path.join(tmpDir, 'openspec', 'changes', 'existing-child', '.openspec.yaml'),
      'utf-8',
    );
    expect(meta).toContain('parent: parent-change');
  });
});
