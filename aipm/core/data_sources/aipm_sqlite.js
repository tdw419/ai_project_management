/**
 * AIPMSQLiteSource: Fetches project state and prompt logs from truths.db.
 */
const BaseDataSource = require('./base');
const Database = require('better-sqlite3');
const { execSync } = require('child_process');
const path = require('path');

class AIPMSQLiteSource extends BaseDataSource {
  constructor(ctx, options = {}) {
    super(ctx, options);
    this.dbPath = options.dbPath || path.resolve(process.cwd(), 'data/truths.db');
    this.repo = options.repo || 'tdw419/ai_project_management';
    this.db = null;
    this.pollInterval = null;
  }

  async initialize() {
    console.log(`LOG: [AIPM_SOURCE] Connecting to ${this.dbPath}...`);
    try {
      this.db = new Database(this.dbPath, { readonly: true, fileMustExist: true });
      await this.poll();
      this.pollInterval = setInterval(() => this.poll(), this.options.interval || 30000);
    } catch (err) {
      console.error(`ERROR: [AIPM_SOURCE] ${err.message}`);
    }
  }

  async poll() {
    if (!this.db) return;
    console.log('LOG: [AIPM_SOURCE] Syncing SQLite + GitHub...');
    
    this.syncProjects();
    this.syncPromptLogs();
    this.syncGitHubQueue();
    
    this.data.lastSync = new Date().toISOString();
    this.ctx.emit('bridge:sync_complete', this.data);
  }

  syncProjects() {
    try {
      const projects = this.db.prepare(`
        SELECT p1.* 
        FROM project_state p1
        INNER JOIN (
          SELECT project_id, MAX(timestamp) as max_ts
          FROM project_state
          GROUP BY project_id
        ) p2 ON p1.project_id = p2.project_id AND p1.timestamp = p2.max_ts
      `).all();

      this.data.projects = projects.map(p => ({
        id: `project:${p.project_id}`,
        type: 'project',
        data: {
          name: p.project_id,
          health: p.health || 'unknown',
          updated_at: p.timestamp,
          commit: p.commit_hash,
          tests: { passing: p.test_passing, total: p.test_total },
          failures: p.consecutive_failures || 0
        }
      }));
    } catch (err) {
      console.warn(`WARN: [AIPM_SOURCE] Project sync failed: ${err.message}`);
    }
  }

  syncPromptLogs() {
    try {
      const logs = this.db.prepare('SELECT * FROM prompt_log ORDER BY timestamp DESC LIMIT 20').all();
      this.data.logs = logs.map(log => ({
        id: `log:${log.id}`,
        type: 'activity',
        data: {
          project: log.project,
          issue: log.issue_number,
          timestamp: log.timestamp,
          outcome: log.outcome_status,
          files_changed: log.files_changed,
          attempt: log.attempt_number
        }
      }));
    } catch (err) {
      console.warn(`WARN: [AIPM_SOURCE] Log sync failed: ${err.message}`);
    }
  }

  syncGitHubQueue() {
    try {
      const output = execSync(`gh issue list --repo ${this.repo} --json number,title,labels,state,updatedAt,body --limit 50`, { encoding: 'utf-8' });
      const issues = JSON.parse(output);
      this.data.issues = issues.map(issue => ({
        id: `issue:${issue.number}`,
        type: 'task',
        data: {
          number: issue.number,
          title: issue.title,
          status: issue.state,
          labels: issue.labels.map(l => l.name),
          updated_at: issue.updatedAt,
          body: issue.body
        }
      }));
    } catch (err) {
      console.warn(`WARN: [AIPM_SOURCE] GitHub sync failed: ${err.message}`);
    }
  }

  stop() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    if (this.db) this.db.close();
  }
}

module.exports = AIPMSQLiteSource;
