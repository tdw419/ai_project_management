/**
 * OpenSpec Bridge -- uses the openspec CLI to manage specs.
 *
 * Instead of reimplementing spec parsing in Python (v2), we shell out to
 * `openspec list --json`, `openspec status --json`, and `openspec instructions`
 * to get structured data. OpenSpec IS the source of truth for specs.
 *
 * This module also handles writing task status back to tasks.md files,
 * since OpenSpec doesn't have a "mark task done" command yet.
 */

import { execFile } from 'child_process';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { join, resolve } from 'path';
import { existsSync } from 'fs';

export interface ChangeInfo {
  name: string;
  completedTasks: number;
  totalTasks: number;
  lastModified: string;
  status: 'complete' | 'in-progress' | 'no-tasks' | 'draft';
}

export interface TaskStep {
  id: string;        // e.g. "1.1"
  description: string;
  completed: boolean;
}

export interface TaskSection {
  id: string;        // e.g. "1" or "SEC-1"
  title: string;
  steps: TaskStep[];
  /** Derived status from steps */
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
}

export interface ParsedChange {
  name: string;
  sections: TaskSection[];
  /** Total steps across all sections */
  totalSteps: number;
  /** Completed steps */
  completedSteps: number;
}

export class OpenSpecBridge {
  private openspecBin: string;

  constructor(openspecBin?: string) {
    this.openspecBin = openspecBin || 'openspec';
  }

  /**
   * List all changes with their completion status.
   * Uses `openspec list --json`.
   */
  async listChanges(projectPath: string): Promise<ChangeInfo[]> {
    const result = await this.run(projectPath, ['list', '--json']);
    const data = JSON.parse(result);
    return data.changes || [];
  }

  /**
   * Get the next pending task from a project's openspec changes.
   * Reads tasks.md files directly (OpenSpec doesn't expose this via CLI).
   */
  async getNextPendingTask(projectPath: string): Promise<ParsedChange | null> {
    const changes = await this.listChanges(projectPath);
    const changesDir = join(projectPath, 'openspec', 'changes');

    for (const change of changes) {
      if (change.status === 'complete') continue;

      const tasksFile = join(changesDir, change.name, 'tasks.md');
      if (!existsSync(tasksFile)) continue;

      const parsed = await this.parseTasksMd(tasksFile, change.name);
      if (!parsed) continue;

      // Find first section with incomplete steps
      const nextSection = parsed.sections.find(
        s => s.status === 'pending' || s.status === 'in_progress'
      );
      if (nextSection) {
        return {
          ...parsed,
          // Only return the first actionable section
          sections: [nextSection],
        };
      }
    }
    return null;
  }

  /**
   * Generate instructions for a specific task using OpenSpec's built-in
   * instruction generator. Falls back to manual prompt building if
   * OpenSpec can't handle it.
   */
  async generateInstructions(
    projectPath: string,
    changeName: string,
  ): Promise<string | null> {
    try {
      // Try OpenSpec's instruction generator
      const result = await this.run(projectPath, [
        'instructions', 'tasks', '--change', changeName,
      ]);
      return result;
    } catch {
      // OpenSpec couldn't generate instructions -- build manually
      return null;
    }
  }

  /**
   * Mark a step as completed in tasks.md.
   * Directly edits the markdown checkbox.
   */
  async completeStep(
    projectPath: string,
    changeName: string,
    stepId: string,
  ): Promise<boolean> {
    const tasksFile = join(
      projectPath, 'openspec', 'changes', changeName, 'tasks.md'
    );
    if (!existsSync(tasksFile)) return false;

    const content = await readFile(tasksFile, 'utf-8');
    // Match "- [ ] X.Y description" and check it off
    const pattern = new RegExp(
      `( - \\[) (] ${stepId.replace('.', '\\.')} )`,
      'g'
    );
    const newContent = content.replace(pattern, '$1x$2');
    if (newContent === content) return false;

    await writeFile(tasksFile, newContent);
    return true;
  }

  /**
   * Mark an entire section as completed in tasks.md.
   */
  async completeSection(
    projectPath: string,
    changeName: string,
    sectionId: string,
  ): Promise<boolean> {
    const tasksFile = join(
      projectPath, 'openspec', 'changes', changeName, 'tasks.md'
    );
    if (!existsSync(tasksFile)) return false;

    const content = await readFile(tasksFile, 'utf-8');

    // Find the section heading
    const sectionPattern = new RegExp(
      `##\\s+${sectionId.replace(/^SEC-/, '')}\\.\\s+(.+)`,
    );
    const match = sectionPattern.exec(content);
    if (!match) return false;

    // Find the block from this heading to the next ## or end
    const blockStart = match.index;
    const nextSection = /\n##\s+\d+\./.exec(content.slice(match.index + match[0].length));
    const blockEnd = nextSection
      ? match.index + match[0].length + nextSection.index
      : content.length;

    const before = content.slice(0, blockStart);
    const block = content.slice(blockStart, blockEnd);
    const after = content.slice(blockEnd);

    // Check all unchecked steps
    const newBlock = block.replace(/- \[ \]/g, '- [x]');
    await writeFile(tasksFile, before + newBlock + after);
    return true;
  }

  /**
   * Create a new change directory with proposal and tasks.
   * For when agents discover out-of-scope work.
   */
  async createChange(
    projectPath: string,
    slug: string,
    proposal: { title: string; summary: string; dependencies?: string },
    tasks: { sections: { title: string; steps: string[] }[] },
  ): Promise<string> {
    const changeDir = join(projectPath, 'openspec', 'changes', slug);
    await mkdir(changeDir, { recursive: true });

    // Write proposal.md
    const proposalMd = [
      `# Proposal: ${proposal.title}`,
      '',
      `## Summary`,
      proposal.summary,
      '',
      `## Dependencies`,
      proposal.dependencies || 'None',
      '',
      `## Success Criteria`,
      '- All tasks complete and tests pass',
    ].join('\n');
    await writeFile(join(changeDir, 'proposal.md'), proposalMd);

    // Write tasks.md
    const taskLines: string[] = [`# Tasks: ${proposal.title}`, ''];
    tasks.sections.forEach((section, i) => {
      taskLines.push(`## ${i + 1}. ${section.title}`);
      section.steps.forEach((step, j) => {
        taskLines.push(`- [ ] ${i + 1}.${j + 1} ${step}`);
      });
      taskLines.push('');
    });
    await writeFile(join(changeDir, 'tasks.md'), taskLines.join('\n'));

    return changeDir;
  }

  // ── Internal ──

  private run(cwd: string, args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      const bin = this.openspecBin;
      const useNode = bin.endsWith('.js');
      const cmd = useNode ? 'node' : bin;
      const cmdArgs = useNode ? [bin, ...args] : args;
      execFile(
        cmd, cmdArgs,
        { cwd, timeout: 30000, maxBuffer: 1024 * 1024 },
        (err, stdout, stderr) => {
          if (err) {
            reject(new Error(`openspec ${args.join(' ')}: ${err.message}\n${stderr}`));
          } else {
            resolve(stdout);
          }
        },
      );
    });
  }

  /**
   * Parse tasks.md directly -- handles both OpenSpec formats:
   * - ## N. Section  / - [ ] N.M step
   * - ### [x] TASK-01: description
   */
  private async parseTasksMd(
    filePath: string,
    changeName: string,
  ): Promise<ParsedChange | null> {
    const content = await readFile(filePath, 'utf-8');

    // Try format 2 first: ## N. Section / - [ ] N.M step
    const sections: TaskSection[] = [];
    const sectionPattern = /##\s+(\d+)\.\s+(.+)/g;
    let match: RegExpExecArray | null;

    const sectionMatches: { num: string; title: string; index: number }[] = [];
    while ((match = sectionPattern.exec(content)) !== null) {
      sectionMatches.push({
        num: match[1],
        title: match[2].trim(),
        index: match.index,
      });
    }

    for (let i = 0; i < sectionMatches.length; i++) {
      const sm = sectionMatches[i];
      const start = content.indexOf('\n', sm.index) + 1;
      const end = i + 1 < sectionMatches.length
        ? sectionMatches[i + 1].index
        : content.length;
      const block = content.slice(start, end);

      const steps: TaskStep[] = [];
      const stepPattern = /-\s*\[([ x-])\]\s*(\d+\.\d+)\s+(.+)/g;
      let stepMatch: RegExpExecArray | null;
      let anyFailed = false;
      let allDone = true;

      while ((stepMatch = stepPattern.exec(block)) !== null) {
        const completed = stepMatch[1] === 'x';
        const failed = stepMatch[1] === '-';
        if (!completed) allDone = false;
        if (failed) anyFailed = true;
        steps.push({
          id: stepMatch[2],
          description: stepMatch[3].trim(),
          completed,
        });
      }

      if (steps.length === 0) continue;

      let status: TaskSection['status'] = 'pending';
      if (anyFailed) status = 'failed';
      else if (allDone) status = 'completed';
      else if (steps.some(s => s.completed)) status = 'in_progress';

      sections.push({
        id: sm.num,
        title: sm.title,
        steps,
        status,
      });
    }

    if (sections.length === 0) return null;

    const totalSteps = sections.reduce((sum, s) => sum + s.steps.length, 0);
    const completedSteps = sections.reduce(
      (sum, s) => sum + s.steps.filter(st => st.completed).length, 0
    );

    return { name: changeName, sections, totalSteps, completedSteps };
  }
}
