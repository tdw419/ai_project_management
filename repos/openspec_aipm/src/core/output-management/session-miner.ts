/**
 * Session Miner -- extracts structured data from Hermes state.db.
 *
 * Hermes stores every conversation in SQLite with full message history,
 * token counts, tool calls, and FTS5 search. This module reads that
 * data and produces structured session summaries that AIPM can use for:
 *
 * 1. Prompt optimization -- which prompts led to success?
 * 2. Outcome prediction -- can we predict failure before running?
 * 3. Knowledge extraction -- what did agents learn?
 * 4. Cost tracking -- where are tokens being wasted?
 */

import Database from 'better-sqlite3';
import { resolve, basename } from 'path';

// ── Types ──

export interface MinedSession {
  id: string;
  source: string;
  model: string;
  title: string;
  startedAt: Date;
  endedAt: Date | null;
  messageCount: number;
  toolCallCount: number;
  totalTokens: number;
  estimatedCost: number;

  /** What the agent was asked to do */
  prompt: AgentPrompt | null;
  /** What the agent actually did */
  outcome: AgentOutcome | null;
  /** Classification of the session */
  category: SessionCategory;
}

export type SessionCategory =
  | 'productive'    // >=5 tool calls, >=10 messages, agent made real changes
  | 'no_action'     // <3 tool calls, agent couldn't start or found nothing to do
  | 'api_failure'   // 0 messages but high tokens -- API call failed
  | 'minimal'       // Small interaction, not clearly productive or failed
  | 'conversation'; // User chat, not an agent run

export interface AgentPrompt {
  /** First user message -- the task prompt */
  raw: string;
  /** Extracted project name */
  project: string | null;
  /** Extracted change/task if spec-driven */
  changeName: string | null;
  /** Extracted section if spec-driven */
  sectionId: string | null;
  /** Strategy: fresh, retry, simplify, different_approach */
  strategy: string | null;
  /** Attempt number */
  attemptNumber: number;
  /** Prompt length in chars */
  length: number;
}

export interface AgentOutcome {
  /** Agent's final message */
  summary: string;
  /** Files mentioned as created */
  filesCreated: string[];
  /** Files mentioned as modified */
  filesModified: string[];
  /** Test counts extracted from messages */
  testCountMentions: string[];
  /** Steps completed (SEC-N format) */
  stepsCompleted: string[];
  /** Whether the agent said "Done" or "Complete" */
  claimedSuccess: boolean;
  /** Whether the agent mentioned errors or failures */
  mentionedErrors: boolean;
  /** Tool call breakdown: terminal commands run */
  terminalCommands: number;
  /** Tool call breakdown: file reads */
  fileReads: number;
  /** Tool call breakdown: file writes */
  fileWrites: number;
  /** Duration estimate from message timestamps */
  durationSeconds: number;
}

export interface MiningStats {
  totalSessions: number;
  productive: number;
  noAction: number;
  apiFailures: number;
  totalTokensUsed: number;
  wastedTokens: number;       // tokens from api_failure + no_action sessions
  topProjects: { project: string; sessions: number; successRate: number }[];
  outcomeDistribution: Record<string, number>;
}

// ── Miner ──

export class SessionMiner {
  private db: Database.Database;

  constructor(stateDbPath?: string) {
    const path = stateDbPath || resolve(
      process.env.HOME || '/home/jericho',
      '.hermes/state.db'
    );
    this.db = new Database(path, { readonly: true });
  }

  close(): void {
    this.db.close();
  }

  /**
   * Get overall mining stats.
   */
  getStats(): MiningStats {
    const rows = this.db.prepare(`
      SELECT
        message_count,
        tool_call_count,
        input_tokens + output_tokens as total_tokens,
        source
      FROM sessions
    `).all() as any[];

    let productive = 0, noAction = 0, apiFailures = 0, totalTokens = 0, wastedTokens = 0;

    for (const r of rows) {
      const tokens = r.total_tokens || 0;
      totalTokens += tokens;

      if (r.message_count === 0) {
        apiFailures++;
        wastedTokens += tokens;
      } else if (r.tool_call_count < 3 && r.message_count < 5) {
        noAction++;
        wastedTokens += tokens;
      } else if (r.tool_call_count >= 5 && r.message_count >= 10) {
        productive++;
      }
    }

    return {
      totalSessions: rows.length,
      productive,
      noAction,
      apiFailures,
      totalTokensUsed: totalTokens,
      wastedTokens,
      topProjects: [],
      outcomeDistribution: {},
    };
  }

  /**
   * Mine sessions within a date range.
   */
  mineSessions(options?: {
    since?: Date;
    limit?: number;
    category?: SessionCategory;
  }): MinedSession[] {
    const { since, limit = 50, category } = options || {};

    let query = `
      SELECT s.*,
             input_tokens + output_tokens as total_tokens
      FROM sessions s
      WHERE 1=1
    `;
    const params: any[] = [];

    if (since) {
      query += ` AND s.started_at >= ?`;
      params.push(since.getTime() / 1000);
    }

    query += ` ORDER BY s.started_at DESC LIMIT ?`;
    params.push(limit);

    const sessions = this.db.prepare(query).all(...params) as any[];
    const results: MinedSession[] = [];

    for (const s of sessions) {
      const cat = this.classifySession(s);
      if (category && cat !== category) continue;

      const prompt = this.extractPrompt(s.id);
      const outcome = this.extractOutcome(s.id);

      results.push({
        id: s.id,
        source: s.source,
        model: s.model,
        title: s.title,
        startedAt: new Date(s.started_at * 1000),
        endedAt: s.ended_at ? new Date(s.ended_at * 1000) : null,
        messageCount: s.message_count,
        toolCallCount: s.tool_call_count,
        totalTokens: s.total_tokens || 0,
        estimatedCost: s.estimated_cost_usd || 0,
        prompt,
        outcome,
        category: cat,
      });
    }

    return results;
  }

  /**
   * Find sessions that worked on a specific project/change.
   */
  findByProject(projectName: string): MinedSession[] {
    const sessions = this.db.prepare(`
      SELECT m.session_id
      FROM messages m
      WHERE m.role = 'user'
        AND m.content LIKE ?
      GROUP BY m.session_id
      ORDER BY m.timestamp DESC
    `).all(`%PROJECT: ${projectName}%`) as any[];

    return sessions.map(s => {
      const session = this.db.prepare(
        `SELECT * FROM sessions WHERE id = ?`
      ).get(s.session_id) as any;
      return this.enrichSession(session);
    }).filter(Boolean);
  }

  /**
   * Get the final assistant message from a session -- the outcome summary.
   */
  getFinalMessage(sessionId: string): string | null {
    const row = this.db.prepare(`
      SELECT content FROM messages
      WHERE session_id = ? AND role = 'assistant'
      ORDER BY timestamp DESC LIMIT 1
    `).get(sessionId) as any;
    return row?.content || null;
  }

  /**
   * Search session content with FTS5.
   */
  search(query: string, limit = 10): { sessionId: string; snippet: string }[] {
    const rows = this.db.prepare(`
      SELECT m.session_id, snippet(messages_fts, -1, '>>>', '<<<', '...', 20) as snippet
      FROM messages_fts f
      JOIN messages m ON m.id = f.rowid
      WHERE messages_fts MATCH ?
      ORDER BY m.timestamp DESC
      LIMIT ?
    `).all(query, limit) as any[];

    return rows.map(r => ({
      sessionId: r.session_id,
      snippet: r.snippet || '',
    }));
  }

  // ── Internal ──

  private classifySession(s: any): SessionCategory {
    if (s.source !== 'cli') return 'conversation';
    if (s.message_count === 0 && (s.total_tokens || 0) > 10000) return 'api_failure';
    if (s.message_count === 0) return 'api_failure';
    if (s.tool_call_count < 3 && s.message_count < 5) return 'no_action';
    if (s.tool_call_count >= 5 && s.message_count >= 10) return 'productive';
    return 'minimal';
  }

  private extractPrompt(sessionId: string): AgentPrompt | null {
    const row = this.db.prepare(`
      SELECT content FROM messages
      WHERE session_id = ? AND role = 'user'
      ORDER BY timestamp ASC LIMIT 1
    `).get(sessionId) as any;

    if (!row?.content) return null;
    const raw = row.content;

    // Extract project name
    const projectMatch = raw.match(/PROJECT:\s*(\S+)/);
    const project = projectMatch ? projectMatch[1] : null;

    // Extract spec change
    const changeMatch = raw.match(/SPEC CHANGE:\s*(.+?)(?:\n|$)/);
    const changeName = changeMatch ? changeMatch[1].trim() : null;

    // Extract section
    const sectionMatch = raw.match(/TASK:\s*SEC-(\d+)/i)
      || raw.match(/TASK:\s*(\d+)\./);
    const sectionId = sectionMatch ? sectionMatch[1] : null;

    // Extract strategy
    const strategyMatch = raw.match(/strategy[=:]\s*(\w+)/i)
      || raw.match(/Strategy:\s*(\w+)/);
    const strategy = strategyMatch ? strategyMatch[1].toLowerCase() : null;

    // Extract attempt number
    const attemptMatch = raw.match(/attempt[ #:]*(\d+)/i);
    const attemptNumber = attemptMatch ? parseInt(attemptMatch[1]) : 1;

    return {
      raw,
      project,
      changeName,
      sectionId,
      strategy,
      attemptNumber,
      length: raw.length,
    };
  }

  private extractOutcome(sessionId: string): AgentOutcome | null {
    // Get all messages for this session
    const messages = this.db.prepare(`
      SELECT role, content, tool_calls, timestamp
      FROM messages
      WHERE session_id = ?
      ORDER BY timestamp ASC
    `).all(sessionId) as any[];

    if (messages.length === 0) return null;

    // Get final assistant message
    const finalAssistant = [...messages].reverse().find(m => m.role === 'assistant');
    const summary = finalAssistant?.content || '';

    // Count tool calls and extract file touched
    let terminalCommands = 0, fileReads = 0, fileWrites = 0;
    const filesCreated: string[] = [];
    const filesModified: string[] = [];
    const testCountMentions: string[] = [];
    const learningsWrites: string[] = [];

    for (const m of messages) {
      if (m.tool_calls) {
        try {
          const calls = JSON.parse(m.tool_calls);
          for (const c of calls) {
            const name = c?.function?.name || '';
            const args = c?.function?.arguments ? JSON.parse(c.function.arguments) : {};

            if (name === 'terminal') {
              terminalCommands++;
              // Check if they are appending to learnings.md via cat or echo
              if (args.command?.includes('learnings.md')) {
                learningsWrites.push(args.command);
              }
            } else if (name === 'read_file' || name === 'search_files') {
              fileReads++;
            } else if (name === 'write_file' || name === 'patch' || name === 'replace') {
              fileWrites++;
              const path = args.file_path || args.path || args.file;
              if (path) {
                if (path.includes('learnings.md')) {
                  learningsWrites.push(args.content || args.new_string || '');
                }
                filesModified.push(path);
              }
            }
          }
        } catch { /* skip */ }
      }

      if (m.role === 'tool' && m.content) {
        // Test count mentions (e.g. "1850/1850 tests passing")
        const testMatches = m.content.match(/\d+\/\d+\s+tests?\s+passing/gi);
        if (testMatches) testCountMentions.push(...testMatches);
      }
    }

    // Combine extracted learnings writes into the summary for the extractor
    let extendedSummary = summary;
    if (learningsWrites.length > 0) {
      extendedSummary += "\n\n### EXTRACTED TOOL-SIDE LEARNINGS:\n" + learningsWrites.join('\n');
    }

    // Extract completed steps
    const stepMatches = summary.match(/SEC-\d+/g) as string[] || [];
    const stepsCompleted = [...new Set(stepMatches)];

    // Detect success/failure signals
    const claimedSuccess = /\b(Done|Complete|All (?:steps )?(?:completed|done)|implemented)\b/i.test(summary);
    const mentionedErrors = /\b(Error|Failed|failed|failure|bug|crash|broken)\b/i.test(summary);

    // Calculate duration
    const timestamps = this.db.prepare(`
      SELECT MIN(timestamp) as first, MAX(timestamp) as last
      FROM messages WHERE session_id = ?
    `).get(sessionId) as any;
    const durationSeconds = timestamps?.first && timestamps?.last ? Math.round(timestamps.last - timestamps.first) : 0;

    return {
      summary: extendedSummary.slice(0, 5000),
      filesCreated: [...new Set(filesCreated)],
      filesModified: [...new Set(filesModified)],
      testCountMentions: [...new Set(testCountMentions)],
      stepsCompleted,
      claimedSuccess,
      mentionedErrors,
      terminalCommands,
      fileReads,
      fileWrites,
      durationSeconds,
    };
  }

  private enrichSession(s: any): MinedSession {
    if (!s) return null as any;
    return {
      id: s.id,
      source: s.source,
      model: s.model,
      title: s.title,
      startedAt: new Date(s.started_at * 1000),
      endedAt: s.ended_at ? new Date(s.ended_at * 1000) : null,
      messageCount: s.message_count,
      toolCallCount: s.tool_call_count,
      totalTokens: (s.input_tokens || 0) + (s.output_tokens || 0),
      estimatedCost: s.estimated_cost_usd || 0,
      prompt: this.extractPrompt(s.id),
      outcome: this.extractOutcome(s.id),
      category: this.classifySession(s),
    };
  }
}
