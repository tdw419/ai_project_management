import { promises as fs } from 'fs';
import path from 'path';
import { JsonConverter } from '../core/converters/json-converter.js';
import { Validator } from '../core/validation/validator.js';
import { ChangeParser } from '../core/parsers/change-parser.js';
import { Change } from '../core/schemas/index.js';
import { isInteractive } from '../utils/interactive.js';
import { getActiveChangeIds } from '../utils/item-discovery.js';
import { readChangeMetadata } from '../utils/change-metadata.js';
import type { ChangeMetadata } from '../core/artifact-graph/types.js';
import { validateStack, topologicalSort } from '../core/validation/stack-validator.js';

// Constants for better maintainability
const ARCHIVE_DIR = 'archive';
const TASK_PATTERN = /^[-*]\s+\[[\sx]\]/i;
const COMPLETED_TASK_PATTERN = /^[-*]\s+\[x\]/i;

export class ChangeCommand {
  private converter: JsonConverter;

  constructor() {
    this.converter = new JsonConverter();
  }

  /**
   * Show a change proposal.
   * - Text mode: raw markdown passthrough (no filters)
   * - JSON mode: minimal object with deltas; --deltas-only returns same object with filtered deltas
   *   Note: --requirements-only is deprecated alias for --deltas-only
   */
  async show(changeName?: string, options?: { json?: boolean; requirementsOnly?: boolean; deltasOnly?: boolean; noInteractive?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');

    if (!changeName) {
      const canPrompt = isInteractive(options);
      const changes = await this.getActiveChanges(changesPath);
      if (canPrompt && changes.length > 0) {
        const { select } = await import('@inquirer/prompts');
        const selected = await select({
          message: 'Select a change to show',
          choices: changes.map(id => ({ name: id, value: id })),
        });
        changeName = selected;
      } else {
        if (changes.length === 0) {
          console.error('No change specified. No active changes found.');
        } else {
          console.error(`No change specified. Available IDs: ${changes.join(', ')}`);
        }
        console.error('Hint: use "openspec change list" to view available changes.');
        process.exitCode = 1;
        return;
      }
    }

    const proposalPath = path.join(changesPath, changeName, 'proposal.md');

    try {
      await fs.access(proposalPath);
    } catch {
      throw new Error(`Change "${changeName}" not found at ${proposalPath}`);
    }

    if (options?.json) {
      const jsonOutput = await this.converter.convertChangeToJson(proposalPath);

      if (options.requirementsOnly) {
        console.error('Flag --requirements-only is deprecated; use --deltas-only instead.');
      }

      const parsed: Change = JSON.parse(jsonOutput);
      const contentForTitle = await fs.readFile(proposalPath, 'utf-8');
      const title = this.extractTitle(contentForTitle, changeName);
      const id = parsed.name;
      const deltas = parsed.deltas || [];

      if (options.requirementsOnly || options.deltasOnly) {
        const output = { id, title, deltaCount: deltas.length, deltas };
        console.log(JSON.stringify(output, null, 2));
      } else {
        const output = {
          id,
          title,
          deltaCount: deltas.length,
          deltas,
        };
        console.log(JSON.stringify(output, null, 2));
      }
    } else {
      const content = await fs.readFile(proposalPath, 'utf-8');
      console.log(content);
    }
  }

  /**
   * List active changes.
   * - Text default: IDs only; --long prints minimal details (title, counts)
   * - JSON: array of { id, title, deltaCount, taskStatus }, sorted by id
   */
  async list(options?: { json?: boolean; long?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');
    
    const changes = await this.getActiveChanges(changesPath);
    
    if (options?.json) {
      const changeDetails = await Promise.all(
        changes.map(async (changeName) => {
          const proposalPath = path.join(changesPath, changeName, 'proposal.md');
          const tasksPath = path.join(changesPath, changeName, 'tasks.md');
          
          try {
            const content = await fs.readFile(proposalPath, 'utf-8');
            const changeDir = path.join(changesPath, changeName);
            const parser = new ChangeParser(content, changeDir);
            const change = await parser.parseChangeWithDeltas(changeName);
            
            let taskStatus = { total: 0, completed: 0 };
            try {
              const tasksContent = await fs.readFile(tasksPath, 'utf-8');
              taskStatus = this.countTasks(tasksContent);
            } catch (error) {
              // Tasks file may not exist, which is okay
              if (process.env.DEBUG) {
                console.error(`Failed to read tasks file at ${tasksPath}:`, error);
              }
            }
            
            return {
              id: changeName,
              title: this.extractTitle(content, changeName),
              deltaCount: change.deltas.length,
              taskStatus,
            };
          } catch (error) {
            return {
              id: changeName,
              title: 'Unknown',
              deltaCount: 0,
              taskStatus: { total: 0, completed: 0 },
            };
          }
        })
      );
      
      const sorted = changeDetails.sort((a, b) => a.id.localeCompare(b.id));
      console.log(JSON.stringify(sorted, null, 2));
    } else {
      if (changes.length === 0) {
        console.log('No items found');
        return;
      }
      const sorted = [...changes].sort();
      if (!options?.long) {
        // IDs only
        sorted.forEach(id => console.log(id));
        return;
      }

      // Long format: id: title and minimal counts
      for (const changeName of sorted) {
        const proposalPath = path.join(changesPath, changeName, 'proposal.md');
        const tasksPath = path.join(changesPath, changeName, 'tasks.md');
        try {
          const content = await fs.readFile(proposalPath, 'utf-8');
          const title = this.extractTitle(content, changeName);
          let taskStatusText = '';
          try {
            const tasksContent = await fs.readFile(tasksPath, 'utf-8');
            const { total, completed } = this.countTasks(tasksContent);
            taskStatusText = ` [tasks ${completed}/${total}]`;
          } catch (error) {
            if (process.env.DEBUG) {
              console.error(`Failed to read tasks file at ${tasksPath}:`, error);
            }
          }
          const changeDir = path.join(changesPath, changeName);
          const parser = new ChangeParser(await fs.readFile(proposalPath, 'utf-8'), changeDir);
          const change = await parser.parseChangeWithDeltas(changeName);
          const deltaCountText = ` [deltas ${change.deltas.length}]`;
          console.log(`${changeName}: ${title}${deltaCountText}${taskStatusText}`);
        } catch {
          console.log(`${changeName}: (unable to read)`);
        }
      }
    }
  }

  async validate(changeName?: string, options?: { strict?: boolean; json?: boolean; noInteractive?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');
    
    if (!changeName) {
      const canPrompt = isInteractive(options);
      const changes = await getActiveChangeIds();
      if (canPrompt && changes.length > 0) {
        const { select } = await import('@inquirer/prompts');
        const selected = await select({
          message: 'Select a change to validate',
          choices: changes.map(id => ({ name: id, value: id })),
        });
        changeName = selected;
      } else {
        if (changes.length === 0) {
          console.error('No change specified. No active changes found.');
        } else {
          console.error(`No change specified. Available IDs: ${changes.join(', ')}`);
        }
        console.error('Hint: use "openspec change list" to view available changes.');
        process.exitCode = 1;
        return;
      }
    }
    
    const changeDir = path.join(changesPath, changeName);
    
    try {
      await fs.access(changeDir);
    } catch {
      throw new Error(`Change "${changeName}" not found at ${changeDir}`);
    }
    
    const validator = new Validator(options?.strict || false);
    const report = await validator.validateChangeDeltaSpecs(changeDir);
    
    if (options?.json) {
      console.log(JSON.stringify(report, null, 2));
    } else {
      if (report.valid) {
        console.log(`Change "${changeName}" is valid`);
      } else {
        console.error(`Change "${changeName}" has issues`);
        report.issues.forEach(issue => {
          const label = issue.level === 'ERROR' ? 'ERROR' : 'WARNING';
          const prefix = issue.level === 'ERROR' ? '✗' : '⚠';
          console.error(`${prefix} [${label}] ${issue.path}: ${issue.message}`);
        });
        // Next steps footer to guide fixing issues
        this.printNextSteps();
        if (!options?.json) {
          process.exitCode = 1;
        }
      }
    }
  }

  /**
   * Display dependency order for active changes (DAG visualization).
   * Validates for cycles first; when cycles are present, fails with the
   * same deterministic cycle error as stack-aware validation.
   */
  async graph(options?: { json?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');
    const changeIds = await this.getActiveChanges(changesPath);

    if (changeIds.length === 0) {
      if (options?.json) {
        console.log(JSON.stringify({ order: [], issues: [] }, null, 2));
      } else {
        console.log('No active changes found.');
      }
      return;
    }

    // Load metadata for each change
    const changeMap: Record<string, ChangeMetadata> = {};
    for (const id of changeIds) {
      const changeDir = path.join(changesPath, id);
      const metadata = readChangeMetadata(changeDir);
      if (metadata) {
        changeMap[id] = metadata;
      } else {
        changeMap[id] = { schema: 'spec-driven' } as ChangeMetadata;
      }
    }

    // Validate for cycles first
    const validationResult = validateStack(changeMap);
    const { order } = topologicalSort(changeMap);

    if (options?.json) {
      console.log(JSON.stringify({ order, issues: validationResult.issues }, null, 2));
    } else {
      if (!validationResult.valid) {
        console.error('Dependency graph has errors:');
        for (const issue of validationResult.issues) {
          if (issue.level === 'ERROR') {
            console.error(`  ✗ ${issue.message}`);
          }
        }
        process.exitCode = 1;
        return;
      }

      // Display dependency order as a simple text tree
      const depsOf = (id: string): string[] => {
        return changeMap[id]?.dependsOn?.filter(d => d in changeMap) ?? [];
      };

      // Build depth map
      const depthMap = new Map<string, number>();
      const visited = new Set<string>();
      const getDepth = (id: string): number => {
        if (depthMap.has(id)) return depthMap.get(id)!;
        if (visited.has(id)) return 0; // shouldn't happen after cycle check
        visited.add(id);
        const deps = depsOf(id);
        const depth = deps.length === 0 ? 0 : Math.max(...deps.map(getDepth)) + 1;
        depthMap.set(id, depth);
        return depth;
      };
      for (const id of order) {
        getDepth(id);
      }

      console.log('Dependency order:');
      for (const id of order) {
        const depth = depthMap.get(id) ?? 0;
        const deps = depsOf(id);
        const indent = '  '.repeat(depth);
        const depStr = deps.length > 0 ? ` (depends on: ${deps.join(', ')})` : '';
        console.log(`${indent}${id}${depStr}`);
      }

      // Show warnings if any
      const warnings = validationResult.issues.filter(i => i.level === 'WARNING');
      if (warnings.length > 0) {
        console.error('');
        console.error('Warnings:');
        for (const w of warnings) {
          console.error(`  ⚠ ${w.message}`);
        }
      }
    }
  }

  /**
   * Suggest unblocked changes in recommended order (topological with
   * lexicographic tie-breaking at equal depth).
   */
  async next(options?: { json?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');
    const changeIds = await this.getActiveChanges(changesPath);

    if (changeIds.length === 0) {
      if (options?.json) {
        console.log(JSON.stringify({ ready: [], blocked: [], blockedBy: {} }, null, 2));
      } else {
        console.log('No active changes found.');
      }
      return;
    }

    // Load metadata
    const changeMap: Record<string, ChangeMetadata> = {};
    for (const id of changeIds) {
      const changeDir = path.join(changesPath, id);
      const metadata = readChangeMetadata(changeDir);
      if (metadata) {
        changeMap[id] = metadata;
      } else {
        changeMap[id] = { schema: 'spec-driven' } as ChangeMetadata;
      }
    }

    // Validate first
    const validationResult = validateStack(changeMap);
    const { order } = topologicalSort(changeMap);

    // Separate errored/blocked changes from ready ones
    const errorChanges = new Set<string>();
    for (const issue of validationResult.issues) {
      if (issue.level === 'ERROR') {
        const match = issue.path.match(/^(.+)\/dependsOn$/);
        if (match) errorChanges.add(match[1]);
        // Also mark cycle participants
        if (issue.message.includes('Dependency cycle detected:')) {
          const parts = issue.message.replace('Dependency cycle detected: ', '').split(' → ');
          for (const p of parts) errorChanges.add(p.trim());
        }
      }
    }

    // Ready = in topological order and not errored
    const ready = order.filter(id => !errorChanges.has(id));
    const blocked = order.filter(id => errorChanges.has(id));
    // Changes not in topological order at all (stuck in cycles)
    const remaining = changeIds.filter(id => !order.includes(id)).sort();
    blocked.push(...remaining);

    // Build blockedBy map
    const blockedBy: Record<string, string[]> = {};
    for (const id of blocked) {
      const deps = changeMap[id]?.dependsOn?.filter(d => d in changeMap) ?? [];
      const reasons: string[] = [];
      for (const dep of deps) {
        if (errorChanges.has(dep)) {
          reasons.push(dep);
        } else if (!changeIds.includes(dep)) {
          reasons.push(`${dep} (missing)`);
        }
      }
      if (reasons.length === 0 && errorChanges.has(id)) {
        reasons.push('cyclic dependency');
      }
      if (reasons.length > 0) {
        blockedBy[id] = reasons;
      }
    }

    if (options?.json) {
      console.log(JSON.stringify({ ready, blocked, blockedBy }, null, 2));
    } else {
      if (ready.length > 0) {
        console.log('Ready to work on:');
        for (const id of ready) {
          const deps = changeMap[id]?.dependsOn?.filter(d => d in changeMap) ?? [];
          const depStr = deps.length > 0 ? ` (after: ${deps.join(', ')})` : '';
          console.log(`  ${id}${depStr}`);
        }
      } else {
        console.log('No unblocked changes available.');
      }

      if (blocked.length > 0) {
        console.log('');
        console.log('Blocked:');
        for (const id of blocked) {
          const reasons = blockedBy[id];
          if (reasons && reasons.length > 0) {
            console.log(`  ${id} — blocked by: ${reasons.join(', ')}`);
          } else {
            console.log(`  ${id}`);
          }
        }
      }
    }
  }

  private async getActiveChanges(changesPath: string): Promise<string[]> {
    try {
      const entries = await fs.readdir(changesPath, { withFileTypes: true });
      const result: string[] = [];
      for (const entry of entries) {
        if (!entry.isDirectory() || entry.name.startsWith('.') || entry.name === ARCHIVE_DIR) continue;
        const proposalPath = path.join(changesPath, entry.name, 'proposal.md');
        try {
          await fs.access(proposalPath);
          result.push(entry.name);
        } catch {
          // skip directories without proposal.md
        }
      }
      return result.sort();
    } catch {
      return [];
    }
  }

  private extractTitle(content: string, changeName: string): string {
    const match = content.match(/^#\s+(?:Change:\s+)?(.+)$/im);
    return match ? match[1].trim() : changeName;
  }

  private countTasks(content: string): { total: number; completed: number } {
    const lines = content.split('\n');
    let total = 0;
    let completed = 0;
    
    for (const line of lines) {
      if (line.match(TASK_PATTERN)) {
        total++;
        if (line.match(COMPLETED_TASK_PATTERN)) {
          completed++;
        }
      }
    }
    
    return { total, completed };
  }

  private printNextSteps(): void {
    const bullets: string[] = [];
    bullets.push('- Ensure change has deltas in specs/: use headers ## ADDED/MODIFIED/REMOVED/RENAMED Requirements');
    bullets.push('- Each requirement MUST include at least one #### Scenario: block');
    bullets.push('- Debug parsed deltas: openspec change show <id> --json --deltas-only');
    console.error('Next steps:');
    bullets.forEach(b => console.error(`  ${b}`));
  }
}
