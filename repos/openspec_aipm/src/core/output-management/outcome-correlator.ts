/**
 * Outcome Correlator -- links Hermes sessions to AIPM prompt outcomes.
 *
 * Reads both:
 *   - Hermes state.db (raw conversations)
 *   - AIPM truths.db (processed outcomes from prompt_log)
 *
 * And produces a unified view of what happened, what worked, and what didn't.
 * This is the data foundation for prompt optimization.
 */

import Database from 'better-sqlite3';
import { resolve } from 'path';
import type { MinedSession, AgentPrompt, AgentOutcome } from './session-miner.js';

// ── Types ──

export interface CorrelatedOutcome {
  /** From AIPM prompt_log */
  promptLogId: number;
  project: string;
  outcomeStatus: string;
  testDelta: number;
  filesChanged: number;
  strategy: string;
  attemptNumber: number;
  provider: string;
  timestamp: string;

  /** From Hermes state.db (linked by prompt text matching) */
  hermesSessionId: string | null;
  totalTokens: number;
  toolCallCount: number;
  durationSeconds: number;
  agentSummary: string;
  filesCreated: string[];
  stepsCompleted: string[];
  claimedSuccess: boolean;
}

export interface ProjectMetrics {
  project: string;
  totalAttempts: number;
  successRate: number;
  avgTestDelta: number;
  avgFilesChanged: number;
  totalTokens: number;
  wastedTokens: number;
  /** Most successful prompt patterns */
  topPatterns: PromptPattern[];
  /** Most common failure patterns */
  failurePatterns: PromptPattern[];
}

export interface PromptPattern {
  pattern: string;
  count: number;
  successRate: number;
  avgTestDelta: number;
  examples: string[];
}

export interface TokenWaste {
  sessionId: string;
  category: string;
  tokens: number;
  reason: string;
}

// ── Correlator ──

export class OutcomeCorrelator {
  private hermesDb: Database.Database;
  private aipmDb: Database.Database;

  constructor(hermesDbPath?: string, aipmDbPath?: string) {
    const home = process.env.HOME || '/home/jericho';
    this.hermesDb = new Database(hermesDbPath || resolve(home, '.hermes/state.db'), { readonly: true });
    this.aipmDb = new Database(aipmDbPath || resolve(home, 'zion/projects/aipm/data/truths.db'), { readonly: true });
  }

  close(): void {
    this.hermesDb.close();
    this.aipmDb.close();
  }

  /**
   * Correlate AIPM prompt_log entries with Hermes sessions.
   * Links them by matching the first few chars of the prompt text.
   */
  correlate(options?: { project?: string; limit?: number }): CorrelatedOutcome[] {
    let query = `
      SELECT id, project, outcome_status, test_delta, files_changed,
             prompt_strategy, attempt_number, provider, timestamp,
             substr(prompt_text, 1, 100) as prompt_start
      FROM prompt_log
      WHERE 1=1
    `;
    const params: any[] = [];

    if (options?.project) {
      query += ` AND project = ?`;
      params.push(options.project);
    }

    query += ` ORDER BY timestamp DESC LIMIT ?`;
    params.push(options?.limit || 100);

    const logs = this.aipmDb.prepare(query).all(...params) as any[];
    const results: CorrelatedOutcome[] = [];

    for (const log of logs) {
      // Find matching Hermes session by prompt text
      let hermesSession: any = null;
      if (log.prompt_start && log.prompt_start.length > 10) {
        const escaped = log.prompt_start.replace(/'/g, "''").replace(/%/g, '\\%');
        hermesSession = this.hermesDb.prepare(`
          SELECT s.id, s.input_tokens + s.output_tokens as total_tokens,
                 s.tool_call_count, s.message_count
          FROM sessions s
          JOIN messages m ON m.session_id = s.id AND m.role = 'user'
          WHERE m.content LIKE ? ESCAPE '\\'
          ORDER BY s.started_at DESC LIMIT 1
        `).get(`${escaped}%`) as any;
      }

      // Get outcome details from hermes if found
      let agentSummary = '';
      let filesCreated: string[] = [];
      let stepsCompleted: string[] = [];
      let claimedSuccess = false;
      let durationSeconds = 0;

      if (hermesSession) {
        // Get final assistant message
        const finalMsg = this.hermesDb.prepare(`
          SELECT content FROM messages
          WHERE session_id = ? AND role = 'assistant'
          ORDER BY timestamp DESC LIMIT 1
        `).get(hermesSession.id) as any;

        if (finalMsg?.content) {
          agentSummary = finalMsg.content.slice(0, 500);
          claimedSuccess = /\b(Done|Complete|implemented)\b/i.test(agentSummary);
          stepsCompleted = agentSummary.match(/SEC-\d+/g) || [];
        }

        // Get timestamps for duration
        const timestamps = this.hermesDb.prepare(`
          SELECT MIN(timestamp) as first, MAX(timestamp) as last
          FROM messages WHERE session_id = ?
        `).get(hermesSession.id) as any;
        if (timestamps?.first && timestamps?.last) {
          durationSeconds = Math.round(timestamps.last - timestamps.first);
        }
      }

      results.push({
        promptLogId: log.id,
        project: log.project,
        outcomeStatus: log.outcome_status,
        testDelta: log.test_delta || 0,
        filesChanged: log.files_changed || 0,
        strategy: log.prompt_strategy,
        attemptNumber: log.attempt_number || 1,
        provider: log.provider,
        timestamp: log.timestamp,
        hermesSessionId: hermesSession?.id || null,
        totalTokens: hermesSession?.total_tokens || 0,
        toolCallCount: hermesSession?.tool_call_count || 0,
        durationSeconds,
        agentSummary,
        filesCreated,
        stepsCompleted: [...new Set(stepsCompleted)],
        claimedSuccess,
      });
    }

    return results;
  }

  /**
   * Get historical outcomes for a specific task.
   * Matches by project and change/section markers in the prompt_text.
   */
  getTaskHistory(project: string, changeName: string, sectionId: string): CorrelatedOutcome[] {
    const query = `
      SELECT id, project, outcome_status, test_delta, files_changed,
             prompt_strategy, attempt_number, provider, timestamp,
             substr(prompt_text, 1, 100) as prompt_start
      FROM prompt_log
      WHERE project = ?
        AND prompt_text LIKE ?
        AND (prompt_text LIKE ? OR prompt_text LIKE ?)
      ORDER BY timestamp DESC
    `;
    const logs = this.aipmDb.prepare(query).all(
      project,
      `%SPEC CHANGE: ${changeName}%`,
      `%TASK: SEC-${sectionId}%`,
      `%TASK: ${sectionId}.%` // Also support "1." format
    ) as any[];

    const results: CorrelatedOutcome[] = [];
    for (const log of logs) {
      // Find matching Hermes session
      let hermesSession: any = null;
      if (log.prompt_start && log.prompt_start.length > 10) {
        const escaped = log.prompt_start.replace(/'/g, "''").replace(/%/g, '\\%');
        hermesSession = this.hermesDb.prepare(`
          SELECT s.id, s.input_tokens + s.output_tokens as total_tokens,
                 s.tool_call_count, s.message_count
          FROM sessions s
          JOIN messages m ON m.session_id = s.id AND m.role = 'user'
          WHERE m.content LIKE ? ESCAPE '\\'
          ORDER BY s.started_at DESC LIMIT 1
        `).get(`${escaped}%`) as any;
      }

      results.push({
        promptLogId: log.id,
        project: log.project,
        outcomeStatus: log.outcome_status,
        testDelta: log.test_delta || 0,
        filesChanged: log.files_changed || 0,
        strategy: log.prompt_strategy,
        attemptNumber: log.attempt_number || 1,
        provider: log.provider,
        timestamp: log.timestamp,
        hermesSessionId: hermesSession?.id || null,
        totalTokens: hermesSession?.total_tokens || 0,
        toolCallCount: hermesSession?.tool_call_count || 0,
        durationSeconds: 0, // skipping heavy lookups for history list
        agentSummary: '',
        filesCreated: [],
        stepsCompleted: [],
        claimedSuccess: log.outcome_status === 'success',
      });
    }

    return results;
  }

  /**
   * Get metrics for a specific project.
   */
  getProjectMetrics(project: string): ProjectMetrics {
    const outcomes = this.correlate({ project, limit: 500 });
    const total = outcomes.length;
    const successes = outcomes.filter(o => o.outcomeStatus === 'success').length;
    const totalTestDelta = outcomes.reduce((sum, o) => sum + o.testDelta, 0);
    const totalFilesChanged = outcomes.reduce((sum, o) => sum + o.filesChanged, 0);
    const totalTokens = outcomes.reduce((sum, o) => sum + o.totalTokens, 0);
    const wastedTokens = outcomes
      .filter(o => o.outcomeStatus === 'no_change' || o.outcomeStatus === 'error')
      .reduce((sum, o) => sum + o.totalTokens, 0);

    // Analyze success patterns
    const successOutcomes = outcomes.filter(o => o.outcomeStatus === 'success');
    const failureOutcomes = outcomes.filter(o =>
      o.outcomeStatus === 'no_change' || o.outcomeStatus === 'failure'
    );

    const topPatterns = this.findPatterns(successOutcomes);
    const failurePatterns = this.findPatterns(failureOutcomes);

    return {
      project,
      totalAttempts: total,
      successRate: total > 0 ? successes / total : 0,
      avgTestDelta: total > 0 ? totalTestDelta / total : 0,
      avgFilesChanged: total > 0 ? totalFilesChanged / total : 0,
      totalTokens,
      wastedTokens,
      topPatterns,
      failurePatterns,
    };
  }

  /**
   * Find token waste -- sessions that consumed tokens without producing value.
   */
  findTokenWaste(limit = 20): TokenWaste[] {
    // API failure sessions (high tokens, 0 messages)
    const apiFailures = this.hermesDb.prepare(`
      SELECT id, input_tokens + output_tokens as total_tokens
      FROM sessions
      WHERE message_count = 0 AND (input_tokens + output_tokens) > 10000
      ORDER BY total_tokens DESC LIMIT ?
    `).all(limit) as any[];

    const waste: TokenWaste[] = apiFailures.map(s => ({
      sessionId: s.id,
      category: 'api_failure',
      tokens: s.total_tokens,
      reason: 'API call failed, all tokens wasted',
    }));

    // No-action sessions (agent couldn't start)
    const noAction = this.hermesDb.prepare(`
      SELECT id, message_count, input_tokens + output_tokens as total_tokens
      FROM sessions
      WHERE tool_call_count < 3 AND message_count > 0 AND message_count < 5
      ORDER BY total_tokens DESC LIMIT ?
    `).all(limit) as any[];

    waste.push(...noAction.map(s => ({
      sessionId: s.id,
      category: 'no_action',
      tokens: s.total_tokens,
      reason: `Agent ran ${s.message_count} messages but made <3 tool calls`,
    })));

    return waste.sort((a, b) => b.tokens - a.tokens).slice(0, limit);
  }

  /**
   * Get all projects and their success rates.
   */
  getAllProjectMetrics(): ProjectMetrics[] {
    const projects = this.aipmDb.prepare(`
      SELECT DISTINCT project FROM prompt_log ORDER BY project
    `).all() as any[];

    return projects.map(p => this.getProjectMetrics(p.project));
  }

  // ── Internal ──

  private findPatterns(outcomes: CorrelatedOutcome[]): PromptPattern[] {
    // Group by strategy + attempt number
    const groups = new Map<string, CorrelatedOutcome[]>();

    for (const o of outcomes) {
      const key = `${o.strategy || 'fresh'}:attempt${o.attemptNumber}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(o);
    }

    return [...groups.entries()]
      .map(([pattern, items]) => ({
        pattern,
        count: items.length,
        successRate: items.filter(o => o.outcomeStatus === 'success').length / items.length,
        avgTestDelta: items.reduce((s, o) => s + o.testDelta, 0) / items.length,
        examples: items.slice(0, 3).map(o =>
          `${o.project}: ${o.outcomeStatus} (delta=${o.testDelta})`
        ),
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  }
}
