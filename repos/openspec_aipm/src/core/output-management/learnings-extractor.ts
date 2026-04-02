/**
 * Learnings Extractor -- mines agent final messages for reusable knowledge.
 *
 * When Hermes agents finish a task, they produce a structured summary.
 * This module extracts:
 * - What worked (patterns to repeat)
 * - What failed (patterns to avoid)
 * - Root cause analyses
 * - Architecture decisions made
 * - Test strategies that were effective
 *
 * Output goes into per-project learnings that feed back into future prompts.
 */

import type { MinedSession } from './session-miner.js';
import { writeFile, readFile, mkdir } from 'fs/promises';
import { join, resolve } from 'path';
import { existsSync } from 'fs';

// ── Types ──

export interface ExtractedLearning {
  /** Which session this came from */
  sessionId: string;
  /** Project name */
  project: string;
  /** Change/feature name */
  changeName: string | null;
  /** Section */
  sectionId: string | null;
  /** Category of learning */
  category: 'success_pattern' | 'failure_pattern' | 'rca' | 'architecture_decision' | 'test_strategy';
  /** The learning itself */
  content: string;
  /** Test delta from this session */
  testDelta: number;
  /** Timestamp */
  timestamp: string;
}

export interface ProjectLearnings {
  project: string;
  learnings: ExtractedLearning[];
  /** Generated summary for prompt injection */
  summary: string;
}

// ── Extractor ──

export class LearningsExtractor {
  private dataDir: string;

  constructor(dataDir?: string) {
    this.dataDir = dataDir || '/tmp/openspec_aipm/learnings';
  }

  /**
   * Extract learnings from a set of mined sessions.
   */
  extractFromSessions(sessions: MinedSession[]): ExtractedLearning[] {
    const learnings: ExtractedLearning[] = [];

    for (const session of sessions) {
      if (!session.outcome?.summary) continue;
      if (session.category !== 'productive') continue;

      const summary = session.outcome.summary;
      const prompt = session.prompt;

      // Extract success patterns
      if (session.outcome.claimedSuccess && session.outcome.terminalCommands > 10) {
        learnings.push({
          sessionId: session.id,
          project: prompt?.project ?? 'unknown',
          changeName: prompt?.changeName ?? null,
          sectionId: prompt?.sectionId ?? null,
          category: 'success_pattern',
          content: this.extractSuccessPattern(summary, session),
          testDelta: 0, // Will be filled by correlator
          timestamp: session.startedAt.toISOString(),
        });
      }

      // Extract root cause analyses
      const rcaMatch = summary.match(/Root Cause:?\s*(.+?)(?:\n|$)/is);
      if (rcaMatch) {
        learnings.push({
          sessionId: session.id,
          project: prompt?.project ?? 'unknown',
          changeName: prompt?.changeName ?? null,
          sectionId: prompt?.sectionId ?? null,
          category: 'rca',
          content: rcaMatch[1].trim().slice(0, 500),
          testDelta: 0,
          timestamp: session.startedAt.toISOString(),
        });
      }

      // Extract architecture decisions
      const archPatterns = [
        /Created:\s*\n((?:\s*-\s+.+\n?)+)/,
        /Modified:\s*\n((?:\s*-\s+.+\n?)+)/,
        /Files?(?:\s+modified)?:\s*\n((?:\s*-\s+.+\n?)+)/i,
      ];
      for (const pat of archPatterns) {
        const archMatch = summary.match(pat);
        if (archMatch) {
          learnings.push({
            sessionId: session.id,
            project: prompt?.project ?? 'unknown',
            changeName: prompt?.changeName ?? null,
            sectionId: prompt?.sectionId ?? null,
            category: 'architecture_decision',
            content: archMatch[1].trim().slice(0, 500),
            testDelta: 0,
            timestamp: session.startedAt.toISOString(),
          });
        }
      }

      // Extract test strategies
      const testMatch = summary.match(/(\d+)\/(\d+)\s+tests?\s+passing/);
      if (testMatch && parseInt(testMatch[2]) > 0) {
        learnings.push({
          sessionId: session.id,
          project: prompt?.project ?? 'unknown',
          changeName: prompt?.changeName ?? null,
          sectionId: prompt?.sectionId ?? null,
          category: 'test_strategy',
          content: `Test approach: ${testMatch[0]} after ${session.outcome.terminalCommands} terminal commands, ${session.outcome.fileWrites} file writes, ${session.outcome.fileReads} file reads`,
          testDelta: 0,
          timestamp: session.startedAt.toISOString(),
        });
      }

      // Extract failure patterns
      if (session.outcome.mentionedErrors && !session.outcome.claimedSuccess) {
        learnings.push({
          sessionId: session.id,
          project: prompt?.project ?? 'unknown',
          changeName: prompt?.changeName ?? null,
          sectionId: prompt?.sectionId ?? null,
          category: 'failure_pattern',
          content: this.extractFailurePattern(summary, session),
          testDelta: 0,
          timestamp: session.startedAt.toISOString(),
        });
      }
    }

    return learnings;
  }

  /**
   * Build a prompt-injectable summary of learnings for a project.
   */
  buildLearningsSummary(learnings: ExtractedLearning[], maxChars = 2000): string {
    const byCategory = new Map<string, ExtractedLearning[]>();
    for (const l of learnings) {
      if (!byCategory.has(l.category)) byCategory.set(l.category, []);
      byCategory.get(l.category)!.push(l);
    }

    const lines: string[] = ['### LEARNINGS FROM PAST SESSIONS'];

    const successes = byCategory.get('success_pattern') || [];
    if (successes.length > 0) {
      lines.push('');
      lines.push('**What worked:**');
      for (const s of successes.slice(-5)) {
        lines.push(`- ${s.content.slice(0, 150)}`);
      }
    }

    const failures = byCategory.get('failure_pattern') || [];
    if (failures.length > 0) {
      lines.push('');
      lines.push('**What failed:**');
      for (const f of failures.slice(-5)) {
        lines.push(`- ${f.content.slice(0, 150)}`);
      }
    }

    const rcas = byCategory.get('rca') || [];
    if (rcas.length > 0) {
      lines.push('');
      lines.push('**Root causes found:**');
      for (const r of rcas.slice(-3)) {
        lines.push(`- ${r.content.slice(0, 200)}`);
      }
    }

    const text = lines.join('\n');
    if (text.length > maxChars) {
      return text.slice(0, maxChars) + '\n...(truncated)';
    }
    return text;
  }

  /**
   * Save learnings to disk for a project.
   */
  async saveLearnings(project: string, learnings: ExtractedLearning[]): Promise<void> {
    const dir = join(this.dataDir, project);
    await mkdir(dir, { recursive: true });

    // Append new learnings to the project's learnings file
    const filePath = join(dir, 'learnings.json');
    let existing: ExtractedLearning[] = [];
    if (existsSync(filePath)) {
      try {
        const raw = await readFile(filePath, 'utf-8');
        existing = JSON.parse(raw);
      } catch { /* start fresh */ }
    }

    // Deduplicate by sessionId
    const seen = new Set(existing.map(l => l.sessionId));
    const newLearnings = learnings.filter(l => !seen.has(l.sessionId));
    const all = [...existing, ...newLearnings];

    await writeFile(filePath, JSON.stringify(all, null, 2));

    // Also save a summary file for prompt injection
    const summary = this.buildLearningsSummary(all);
    await writeFile(join(dir, 'summary.md'), summary);
  }

  /**
   * Load existing learnings for a project.
   */
  async loadLearnings(project: string): Promise<ProjectLearnings> {
    const filePath = join(this.dataDir, project, 'learnings.json');
    let learnings: ExtractedLearning[] = [];

    if (existsSync(filePath)) {
      try {
        const raw = await readFile(filePath, 'utf-8');
        learnings = JSON.parse(raw);
      } catch { /* empty */ }
    }

    return {
      project,
      learnings,
      summary: this.buildLearningsSummary(learnings),
    };
  }

  // ── Internal ──

  private extractSuccessPattern(summary: string, session: MinedSession): string {
    // Extract the key accomplishment
    const lines = summary.split('\n').filter(l => l.trim());
    const firstLine = lines[0] || '';

    // Get the steps completed
    const steps = session.outcome?.stepsCompleted || [];
    const toolRatio = session.outcome
      ? `${session.outcome.fileReads}r/${session.outcome.fileWrites}w/${session.outcome.terminalCommands}cmd`
      : 'unknown';

    return `Agent completed ${steps.join(', ')} with ${toolRatio} tool usage. ${firstLine.slice(0, 100)}`;
  }

  private extractFailurePattern(summary: string, session: MinedSession): string {
    // Extract error mentions
    const errorLines = summary.split('\n')
      .filter(l => /error|fail|crash|bug|broken/i.test(l))
      .map(l => l.trim().slice(0, 100));

    if (errorLines.length > 0) {
      return `Errors encountered: ${errorLines.slice(0, 3).join('; ')}`;
    }

    // Fallback: just the first line
    return summary.split('\n')[0]?.slice(0, 200) || 'Unknown failure';
  }
}
