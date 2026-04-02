import { promises as fs } from 'fs';
import path from 'path';
import { JsonConverter } from '../core/converters/json-converter.js';
import { Validator } from '../core/validation/validator.js';
import { ChangeParser } from '../core/parsers/change-parser.js';
import { Change } from '../core/schemas/index.js';
import { isInteractive } from '../utils/interactive.js';
import { getActiveChangeIds } from '../utils/item-discovery.js';
import { readChangeMetadata } from '../utils/change-metadata.js';
import { topologicalSort, getUnblockedChanges, type GraphResult } from '../core/validation/topological-sort.js';
import type { ChangeEntry } from '../core/validation/stack-validator.js';
import { splitChange, findChildren, generateChildIds, type SplitOptions } from '../core/validation/change-splitter.js';

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

  /**
   * Display dependency graph for active changes.
   * Shows topological ordering with depth levels.
   */
  async graph(options?: { json?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');
    const entries = await this.loadChangeEntries(changesPath);

    if (entries.length === 0) {
      if (options?.json) {
        console.log(JSON.stringify({ nodes: [], cycleError: null }, null, 2));
      } else {
        console.log('No active changes found.');
      }
      return;
    }

    const result = topologicalSort(entries);

    if (options?.json) {
      console.log(JSON.stringify(result, null, 2));
      return;
    }

    if (result.cycleError) {
      console.error(`Error: ${result.cycleError}`);
      process.exitCode = 1;
      return;
    }

    // Text rendering
    for (const node of result.nodes) {
      const depStr = node.dependsOn.length > 0
        ? ` <- ${node.dependsOn.join(', ')}`
        : '';
      console.log(`${'  '.repeat(node.depth)}${node.id}${depStr}`);
    }
  }

  /**
   * Suggest unblocked changes in recommended order.
   */
  async next(options?: { json?: boolean }): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');
    const entries = await this.loadChangeEntries(changesPath);

    if (entries.length === 0) {
      if (options?.json) {
        console.log(JSON.stringify({ nodes: [], cycleError: null }, null, 2));
      } else {
        console.log('No active changes found.');
      }
      return;
    }

    const result = getUnblockedChanges(entries);

    if (options?.json) {
      console.log(JSON.stringify(result, null, 2));
      return;
    }

    if (result.cycleError) {
      console.error(`Error: ${result.cycleError}`);
      process.exitCode = 1;
      return;
    }

    if (result.nodes.length === 0) {
      console.log('No unblocked changes available.');
      return;
    }

    for (const node of result.nodes) {
      const depStr = node.dependsOn.length > 0
        ? ` (after: ${node.dependsOn.join(', ')})`
        : '';
      console.log(`${node.id}${depStr}`);
    }
  }

  /**
   * Split a change into child slices.
   * Creates child change directories with parent/dependency metadata
   * and converts the source into a parent planning container.
   */
  async split(
    changeId: string,
    options?: {
      slices?: number;
      names?: string[];
      overwrite?: boolean;
      json?: boolean;
    },
  ): Promise<void> {
    const changesPath = path.join(process.cwd(), 'openspec', 'changes');

    const splitOpts: SplitOptions = {
      changeId,
      slices: options?.slices,
      names: options?.names,
      overwrite: options?.overwrite ?? false,
    };

    const result = await splitChange(changesPath, splitOpts);

    if (result.error) {
      if (options?.json) {
        console.log(JSON.stringify({ error: result.error, parentId: result.parentId, children: [] }, null, 2));
      } else {
        console.error(`Error: ${result.error}`);
      }
      process.exitCode = 1;
      return;
    }

    if (options?.json) {
      console.log(JSON.stringify({
        parentId: result.parentId,
        parentConverted: result.parentConverted,
        children: result.children.map(c => ({
          id: c.id,
          parent: c.metadata.parent,
          dependsOn: c.metadata.dependsOn,
        })),
      }, null, 2));
      return;
    }

    // Text output
    console.log(`Split "${result.parentId}" into ${result.children.length} slices:`);
    for (const child of result.children) {
      console.log(`  - ${child.id} (parent: ${child.metadata.parent}, dependsOn: [${child.metadata.dependsOn?.join(', ')}])`);
    }
    if (result.parentConverted) {
      console.log(`Parent "${result.parentId}" converted to planning container.`);
    }
  }

  /**
   * Load change entries with metadata from the changes directory.
   */
  private async loadChangeEntries(changesPath: string): Promise<ChangeEntry[]> {
    const changeIds = await this.getActiveChanges(changesPath);
    const entries: ChangeEntry[] = [];

    for (const id of changeIds) {
      const changeDir = path.join(changesPath, id);
      try {
        const metadata = readChangeMetadata(changeDir);
        if (metadata) {
          entries.push({ id, metadata });
        }
      } catch {
        // Changes without metadata are still valid entries (backward compatible)
        entries.push({ id, metadata: { schema: 'spec-driven' } });
      }
    }

    return entries;
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
