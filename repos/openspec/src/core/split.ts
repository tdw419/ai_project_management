/**
 * Split Scaffolding — splits a parent change into child slices.
 *
 * Given a change ID (must exist in openspec/changes/), this module:
 * 1. Creates N child change directories under openspec/changes/
 * 2. Each child gets a .openspec.yaml with `parent` pointing back to the source
 * 3. Each child gets a stub proposal.md and tasks.md
 * 4. The source change is marked as a parent planning container
 */

import { promises as fs } from 'fs';
import path from 'path';
import * as yaml from 'yaml';
import { writeChangeMetadata } from '../utils/change-metadata.js';
import type { ChangeMetadata } from './artifact-graph/types.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SplitSlice {
  /** kebab-case ID for the child slice (e.g. "my-feature-part-a") */
  id: string;
  /** Optional human-readable title for the child */
  title?: string;
}

export interface SplitOptions {
  /** Child slices to create */
  slices: SplitSlice[];
  /** When true, allow re-splitting an already-split parent */
  overwrite?: boolean;
}

export interface SplitResult {
  /** IDs of the created child changes */
  childIds: string[];
  /** Path to the parent change directory */
  parentDir: string;
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

/**
 * Read raw metadata YAML (bypassing Zod validation) so we can detect
 * _splitChildren which is not part of the ChangeMetadata schema.
 */
async function readRawMeta(changeDir: string): Promise<Record<string, any> | null> {
  const metaPath = path.join(changeDir, '.openspec.yaml');
  try {
    const content = await fs.readFile(metaPath, 'utf-8');
    return yaml.parse(content) as Record<string, any>;
  } catch {
    return null;
  }
}

/**
 * Split a change into child slices.
 *
 * @param projectRoot - Project root containing openspec/
 * @param changeId - The change to split
 * @param options - Slices and options
 * @returns Result with child IDs and parent dir
 * @throws Error if change not found, already has children (without --overwrite), or slice IDs collide
 */
export async function splitChange(
  projectRoot: string,
  changeId: string,
  options: SplitOptions,
): Promise<SplitResult> {
  const changesDir = path.join(projectRoot, 'openspec', 'changes');
  const parentDir = path.join(changesDir, changeId);

  // 1. Validate parent exists
  const proposalPath = path.join(parentDir, 'proposal.md');
  try {
    await fs.access(proposalPath);
  } catch {
    throw new Error(`Change "${changeId}" not found at ${parentDir}`);
  }

  // 2. Read existing parent metadata (raw, to detect _splitChildren)
  const rawMeta = await readRawMeta(parentDir);

  // 3. Check if already split (has _splitChildren) — error unless overwrite
  if (!options.overwrite && rawMeta?._splitChildren) {
    throw new Error(
      `Change "${changeId}" has already been split. Use --overwrite to re-split.`,
    );
  }

  // 4. Validate slice IDs — no collisions with existing dirs (unless overwrite)
  const childIds: string[] = [];
  for (const slice of options.slices) {
    const childDir = path.join(changesDir, slice.id);
    const exists = await dirExists(childDir);
    if (exists && !options.overwrite) {
      throw new Error(
        `Cannot create slice "${slice.id}": directory already exists. Use --overwrite to replace.`,
      );
    }
    childIds.push(slice.id);
  }

  // 5. If overwrite: remove old child dirs from previous split AND current slices
  if (options.overwrite) {
    const toRemove = new Set<string>();
    // Remove previous split children
    if (rawMeta?._splitChildren && Array.isArray(rawMeta._splitChildren)) {
      for (const id of rawMeta._splitChildren as string[]) {
        toRemove.add(id);
      }
    }
    // Remove current slices if they exist
    for (const id of childIds) {
      toRemove.add(id);
    }
    for (const id of toRemove) {
      const childDir = path.join(changesDir, id);
      if (await dirExists(childDir)) {
        await fs.rm(childDir, { recursive: true, force: true });
      }
    }
  }

  // 6. Create child slices
  for (const slice of options.slices) {
    const childDir = path.join(changesDir, slice.id);
    await fs.mkdir(childDir, { recursive: true });

    // Write .openspec.yaml with parent reference
    writeChangeMetadata(
      childDir,
      {
        schema: rawMeta?.schema ?? 'spec-driven',
        created: new Date().toISOString().split('T')[0],
        parent: changeId,
      },
      projectRoot,
    );

    // Write stub proposal.md
    const proposalContent = [
      `## Why`,
      ``,
      `Slice of "${changeId}". ${slice.title ?? ''}`.trim(),
      ``,
      `## What Changes`,
      ``,
      `_(To be defined)_`,
      ``,
    ].join('\n');
    await fs.writeFile(path.join(childDir, 'proposal.md'), proposalContent, 'utf-8');

    // Write stub tasks.md
    const tasksContent = [
      `## Tasks`,
      ``,
      `- [ ] _(To be defined)_`,
      ``,
    ].join('\n');
    await fs.writeFile(path.join(childDir, 'tasks.md'), tasksContent, 'utf-8');
  }

  // 7. Update parent metadata to mark as split planning container
  const metaToWrite: Record<string, any> = {
    schema: rawMeta?.schema ?? 'spec-driven',
    created: rawMeta?.created ?? new Date().toISOString().split('T')[0],
    // Preserve existing stack fields
    dependsOn: rawMeta?.dependsOn ?? undefined,
    provides: rawMeta?.provides ?? undefined,
    requires: rawMeta?.requires ?? undefined,
    touches: rawMeta?.touches ?? undefined,
    // Mark as parent with children
    _splitChildren: childIds.sort(),
  };

  // Clean up undefined entries
  for (const key of Object.keys(metaToWrite)) {
    if (metaToWrite[key] === undefined) {
      delete metaToWrite[key];
    }
  }

  await fs.writeFile(
    path.join(parentDir, '.openspec.yaml'),
    yaml.stringify(metaToWrite),
    'utf-8',
  );

  return { childIds, parentDir };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function dirExists(dir: string): Promise<boolean> {
  try {
    const stat = await fs.stat(dir);
    return stat.isDirectory();
  } catch {
    return false;
  }
}
