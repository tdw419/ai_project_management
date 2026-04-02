/**
 * Change Split Scaffolding.
 *
 * Decomposes a large change into stackable child slices:
 * - Creates child change directories with parent/dependency metadata
 * - Generates stub proposal/tasks files for each child
 * - Converts the source change into a parent planning container
 * - Prevents accidental re-split unless --overwrite is requested
 */

import { promises as fs } from 'fs';
import path from 'path';
import { readChangeMetadata, writeChangeMetadata } from '../../utils/change-metadata.js';
import type { ChangeMetadata } from '../artifact-graph/types.js';

export interface SplitOptions {
  /** The change ID to split */
  changeId: string;
  /** Number of slices to create (default 2, ignored if names is provided) */
  slices?: number;
  /** Explicit names for child slices */
  names?: string[];
  /** Whether to allow re-splitting an already-split change */
  overwrite: boolean;
}

export interface SplitChild {
  id: string;
  dir: string;
  metadata: ChangeMetadata;
}

export interface SplitResult {
  parentId: string;
  parentConverted: boolean;
  children: SplitChild[];
  error?: string;
}

/**
 * Scan the changes directory for children that reference a given parent.
 */
export async function findChildren(
  changesPath: string,
  parentId: string,
): Promise<string[]> {
  const children: string[] = [];

  try {
    const entries = await fs.readdir(changesPath, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith('.') || entry.name === 'archive') continue;
      try {
        const childDir = path.join(changesPath, entry.name);
        const metadata = readChangeMetadata(childDir);
        if (metadata?.parent === parentId) {
          children.push(entry.name);
        }
      } catch {
        // Skip changes without valid metadata
      }
    }
  } catch {
    // Directory might not exist
  }

  return children.sort();
}

/**
 * Generate child slice IDs from options.
 * Deterministic: same inputs always produce same outputs.
 */
export function generateChildIds(
  parentId: string,
  options: Pick<SplitOptions, 'slices' | 'names'>,
): string[] {
  if (options.names && options.names.length > 0) {
    return options.names.map(name => `${parentId}-${name}`);
  }

  const count = Math.max(2, options.slices ?? 2);
  const ids: string[] = [];
  for (let i = 1; i <= count; i++) {
    ids.push(`${parentId}-slice-${i}`);
  }
  return ids;
}

/**
 * Execute the split operation.
 *
 * 1. Validates the source change exists
 * 2. Checks for existing children (errors unless overwrite)
 * 3. Creates child directories with metadata, proposal, and tasks stubs
 * 4. Converts the source into a parent planning container
 */
export async function splitChange(
  changesPath: string,
  options: SplitOptions,
): Promise<SplitResult> {
  const sourceDir = path.join(changesPath, options.changeId);

  // Step 1: Verify source change exists
  try {
    await fs.access(sourceDir);
  } catch {
    return {
      parentId: options.changeId,
      parentConverted: false,
      children: [],
      error: `Change "${options.changeId}" not found at ${sourceDir}`,
    };
  }

  // Step 2: Check for existing children
  const existingChildren = await findChildren(changesPath, options.changeId);

  if (existingChildren.length > 0 && !options.overwrite) {
    return {
      parentId: options.changeId,
      parentConverted: false,
      children: [],
      error: `Change "${options.changeId}" has already been split into: ${existingChildren.join(', ')}. Use --overwrite to re-split.`,
    };
  }

  // If overwrite, clean up existing children
  if (existingChildren.length > 0 && options.overwrite) {
    for (const childId of existingChildren) {
      const childDir = path.join(changesPath, childId);
      await fs.rm(childDir, { recursive: true, force: true });
    }
  }

  // Step 3: Generate child IDs and create directories
  const childIds = generateChildIds(options.changeId, options);

  // Read source metadata (or use default)
  let sourceMetadata: ChangeMetadata;
  try {
    const existing = readChangeMetadata(sourceDir);
    sourceMetadata = existing ?? { schema: 'spec-driven' };
  } catch {
    sourceMetadata = { schema: 'spec-driven' };
  }

  const children: SplitChild[] = [];

  for (const childId of childIds) {
    const childDir = path.join(changesPath, childId);
    await fs.mkdir(childDir, { recursive: true });

    const childMetadata: ChangeMetadata = {
      schema: sourceMetadata.schema,
      parent: options.changeId,
      dependsOn: [options.changeId],
    };

    // Write child metadata
    writeChangeMetadata(childDir, childMetadata);

    // Write stub proposal
    const proposalContent = [
      `# Proposal: ${childId}`,
      ``,
      `## Summary`,
      `Child slice of "${options.changeId}".`,
      ``,
      `## Dependencies`,
      `- Parent: ${options.changeId}`,
    ].join('\n');
    await fs.writeFile(path.join(childDir, 'proposal.md'), proposalContent, 'utf-8');

    // Write stub tasks
    const tasksContent = [
      `# Tasks: ${childId}`,
      ``,
      `## 1. Implementation`,
      `- [ ] 1.1 Define implementation details`,
    ].join('\n');
    await fs.writeFile(path.join(childDir, 'tasks.md'), tasksContent, 'utf-8');

    children.push({ id: childId, dir: childDir, metadata: childMetadata });
  }

  // Step 4: Convert source into parent planning container
  const sourceProposalPath = path.join(sourceDir, 'proposal.md');
  let sourceProposal = '';
  try {
    sourceProposal = await fs.readFile(sourceProposalPath, 'utf-8');
  } catch {
    sourceProposal = `# Change: ${options.changeId}\n\n## Why\n\n## What Changes\n`;
  }

  // Add split marker (idempotent — won't duplicate on overwrite)
  if (!sourceProposal.includes('**Split into slices:**')) {
    sourceProposal += [
      ``,
      `## Split Status`,
      ``,
      `**Split into slices:** ${childIds.map(id => `\`${id}\``).join(', ')}`,
      ``,
      `This change is a planning container. Implementation work is in child slices.`,
    ].join('\n');
    await fs.writeFile(sourceProposalPath, sourceProposal, 'utf-8');
  }

  return {
    parentId: options.changeId,
    parentConverted: true,
    children,
  };
}
