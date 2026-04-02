/**
 * Integrated Context Manager for openspec_aipm.
 * Coordinates scoring, selection, and retrieval.
 */

import { ContextItem, ContextBudget, PRIORITY } from './types.js';
import { ContextScorer } from './scorer.js';
import { ContextSelector } from './selector.js';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import { join } from 'path';

export class ContextManager {
  private scorer = new ContextScorer();
  private selector = new ContextSelector();

  /**
   * Main entry point to get the best context items within a budget.
   */
  public async getPromptContext(
    projectPath: string,
    projectName: string,
    changeName: string,
    taskDescription: string,
    attemptNumber: number,
    budget: ContextBudget = { totalTokens: 4096, sections: {} }
  ): Promise<ContextItem[]> {
    const rawItems = await this.gatherRawItems(
      projectPath,
      projectName,
      changeName,
      attemptNumber
    );

    const scored = this.scorer.score(rawItems, taskDescription, attemptNumber);
    const selected = this.selector.select(scored, budget);

    // Sort back to a logical order for display (e.g., by priority)
    return selected.sort((a, b) => b.priority - a.priority);
  }

  /**
   * Gathers all available context sources.
   */
  private async gatherRawItems(
    projectPath: string,
    projectName: string,
    changeName: string,
    attemptNumber: number
  ): Promise<ContextItem[]> {
    const items: ContextItem[] = [];

    // 1. Proposal Context
    const proposalPath = join(projectPath, 'openspec', 'changes', changeName, 'proposal.md');
    if (existsSync(proposalPath)) {
      const proposal = await readFile(proposalPath, 'utf-8');
      const whyMatch = proposal.match(/##\s+(?:Why|Problem)\s*\n(.+?)(?=\n##|\n$)/s);
      if (whyMatch) {
        items.push({
          id: 'proposal_why',
          content: whyMatch[1].trim(),
          priority: PRIORITY.MEDIUM,
          tags: ['proposal', 'why']
        });
      }
    }

    // 2. Local Change-level Learnings
    const learningsPath = join(projectPath, 'openspec', 'changes', changeName, 'learnings.md');
    if (existsSync(learningsPath)) {
      const learnings = await readFile(learningsPath, 'utf-8');
      items.push({
        id: 'change_learnings',
        content: learnings.trim(),
        priority: PRIORITY.MEDIUM,
        tags: ['learnings', 'local']
      });
    }

    // 3. Global Project-level Learnings
    const globalLearningsPath = `/tmp/openspec_aipm/learnings/${projectName}/summary.md`;
    if (existsSync(globalLearningsPath)) {
      const globalLearnings = await readFile(globalLearningsPath, 'utf-8');
      items.push({
        id: 'global_learnings',
        content: globalLearnings.trim(),
        priority: PRIORITY.LOW, // Cut these if space is tight
        tags: ['learnings', 'global']
      });
    }

    // 4. Tech Stack / Guidelines
    const techStackPath = join(projectPath, 'conductor', 'tech-stack.md');
    if (existsSync(techStackPath)) {
      const techStack = await readFile(techStackPath, 'utf-8');
      items.push({
        id: 'tech_stack',
        content: techStack.trim(),
        priority: PRIORITY.MEDIUM,
        tags: ['tech-stack', 'guidelines']
      });
    }

    return items;
  }
}
