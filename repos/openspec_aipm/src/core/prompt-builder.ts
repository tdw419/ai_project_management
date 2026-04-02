/**
 * Prompt builder -- constructs the agent prompt from spec data.
 *
 * Uses OpenSpec's instruction generator when available,
 * falls back to manual construction.
 */

import type { ProjectConfig } from '../models/config.js';
import type { Strategy } from '../models/outcome.js';
import type { ParsedChange, OpenSpecBridge } from './openspec-bridge.js';
import { readFile } from 'fs/promises';
import { join } from 'path';
import { existsSync } from 'fs';
import { ContextManager } from './context-management/index.js';
import { PRIORITY } from './context-management/types.js';

export interface PromptContext {
  project: ProjectConfig;
  change: ParsedChange;
  section: TaskSection_;
  testsBefore: [number, number];
  strategy: Strategy;
  attemptNumber: number;
  /** Previous outcome summary (for retries) */
  lastOutcome?: string;
  /** Token budget for the prompt */
  tokenBudget?: number;
}

// Re-export the type from openspec-bridge
import type { TaskSection } from './openspec-bridge.js';
type TaskSection_ = TaskSection;

const contextManager = new ContextManager();

export async function buildPrompt(
  ctx: PromptContext,
  bridge: OpenSpecBridge,
): Promise<string> {
  const { project, change, section, testsBefore, strategy, attemptNumber, tokenBudget = 4096 } = ctx;

  // Build the static base lines (CRITICAL)
  const lines: string[] = [
    `### PROJECT: ${project.name}`,
    `Path: ${project.path}`,
    `Language: ${project.language}`,
    `Status: ${testsBefore[0]}/${testsBefore[1]} tests passing.`,
    '',
    `### SPEC CHANGE: ${change.name}`,
    `### TASK: SEC-${section.id} - ${section.title}`,
  ];

  // Add pending steps (CRITICAL)
  const pendingSteps = section.steps.filter(s => !s.completed);
  if (pendingSteps.length > 0) {
    lines.push('');
    lines.push('Steps:');
    pendingSteps.forEach(s => {
      lines.push(`  - [ ] ${s.id} ${s.description}`);
    });
  }

  // Use ContextManager to pick the best supporting information
  const dynamicContext = await contextManager.getPromptContext(
    project.path,
    project.name,
    change.name,
    section.title + ' ' + pendingSteps.map(s => s.description).join(' '),
    attemptNumber,
    { totalTokens: tokenBudget - 500, sections: {} } // Reserve space for instructions
  );

  // Add the selected context items
  dynamicContext.forEach(item => {
    lines.push('');
    lines.push(`### ${item.id.toUpperCase().replace(/_/g, ' ')}`);
    lines.push(item.content);
  });

  // Retry context (HIGH)
  if (ctx.lastOutcome && attemptNumber > 1) {
    lines.push('');
    lines.push('### PREVIOUS ATTEMPT');
    lines.push(`Last outcome: ${ctx.lastOutcome}`);
    lines.push(`Strategy: ${strategy} (attempt #${attemptNumber})`);
  }

  // Instructions (CRITICAL)
  lines.push('');
  lines.push('### INSTRUCTIONS');
  lines.push(`1. Explore the codebase in ${project.path}`);
  lines.push(`2. Implement task SEC-${section.id} as described above`);
  lines.push(`3. Check off each step in tasks.md as you complete it:`);
  lines.push(`   The spec file is at: openspec/changes/${change.name}/tasks.md`);
  lines.push(`   Change '- [ ] X.Y ...' to '- [x] X.Y ...' after each step is done.`);
  lines.push(`4. Verify with: ${project.testCommand}`);
  lines.push(`5. Commit your changes:`);
  lines.push(`   git add -A`);
  lines.push(`   git commit -m "spec: task SEC-${section.id}"`);
  lines.push(`6. DO NOT modify protected files or break existing tests`);
  if (project.protectedFiles.length > 0) {
    lines.push(`   Protected: ${project.protectedFiles.join(', ')}`);
  }

  // Spec maintenance instructions (ALWAYS)
  lines.push('');
  lines.push('### SPEC MAINTENANCE (IMPORTANT)');
  lines.push('You OWN this spec. Update it as you learn.');
  lines.push('');
  lines.push('A) If the task description or steps are wrong or incomplete:');
  lines.push(`   Edit openspec/changes/${change.name}/tasks.md directly.`);
  lines.push('   Fix incorrect descriptions. Add missing steps. Reorder if needed.');
  lines.push('   Better spec = better outcome for the next agent.');
  lines.push('');
  lines.push('B) If the acceptance criteria don\'t match reality:');
  lines.push(`   Edit openspec/changes/${change.name}/proposal.md.`);
  lines.push('   Update the \'Success Criteria\' or \'Solution\' sections.');
  lines.push('   Document WHY the original was wrong.');
  lines.push('');
  lines.push('C) If you discover work that is clearly out of scope for this task:');
  lines.push('   Do NOT try to shoehorn it into the current task.');
  lines.push('   Instead, create a new change directory:');
  lines.push('     mkdir -p openspec/changes/<descriptive-slug>/');
  lines.push('     Write proposal.md and tasks.md (see format above)');
  lines.push('   The loop will pick it up automatically in the next cycle.');
  lines.push('');
  lines.push('D) After implementation, reflect briefly:');
  lines.push(`   Append to openspec/changes/${change.name}/learnings.md:`);
  lines.push('   What worked, what didn\'t, what would you do differently.');

  return lines.join('\n');
}
