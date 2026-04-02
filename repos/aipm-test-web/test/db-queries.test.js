const { describe, it, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { DatabaseSync } = require('node:sqlite');

const {
  getProjectStates,
  getProjectHistory,
  getRecentMetrics,
  getRecentSessions,
} = require('../src/db/queries');

function createTestDb() {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'truths-q-'));
  const dbPath = path.join(tmpDir, 'test.db');
  const db = new DatabaseSync(dbPath);

  db.exec(`
    CREATE TABLE project_state (
      project_id TEXT, timestamp TEXT, commit_hash TEXT,
      test_passing INTEGER, test_total INTEGER, test_output TEXT,
      features_done_json TEXT, features_next_json TEXT,
      health TEXT, consecutive_failures INTEGER
    );
    INSERT INTO project_state VALUES ('proj-a','2025-01-01T00:00:00Z','abc123',5,5,'','[]','[]','healthy',0);
    INSERT INTO project_state VALUES ('proj-b','2025-01-02T00:00:00Z','def456',3,4,'','[]','[]','degraded',1);
    INSERT INTO project_state VALUES ('proj-a','2025-01-03T00:00:00Z','ghi789',6,6,'','[]','[]','healthy',0);
  `);

  db.exec(`
    CREATE TABLE metrics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL, metric_name TEXT NOT NULL,
      metric_value REAL NOT NULL, tags_json TEXT DEFAULT '{}'
    );
    INSERT INTO metrics VALUES (1,'2025-01-01','cpu',0.5,'{}');
    INSERT INTO metrics VALUES (2,'2025-01-02','mem',0.8,'{}');
    INSERT INTO metrics VALUES (3,'2025-01-03','cpu',0.6,'{}');
  `);

  db.exec(`
    CREATE TABLE session_index (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_file TEXT NOT NULL, session_id TEXT, platform TEXT DEFAULT '',
      project TEXT DEFAULT '', issue_number INTEGER DEFAULT 0,
      started_at TEXT NOT NULL, message_count INTEGER DEFAULT 0,
      files_explored TEXT DEFAULT '[]', files_modified TEXT DEFAULT '[]',
      commands_run TEXT DEFAULT '[]', errors_hit TEXT DEFAULT '[]',
      tools_used TEXT DEFAULT '{}', ollama_summary TEXT DEFAULT '',
      raw_extract TEXT DEFAULT '', indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
      summarized_at TEXT DEFAULT ''
    );
    INSERT INTO session_index (session_file,started_at) VALUES ('sess1.json','2025-01-01T00:00:00Z');
    INSERT INTO session_index (session_file,started_at) VALUES ('sess2.json','2025-01-02T00:00:00Z');
  `);

  db.close();
  return { dbPath, tmpDir };
}

describe('queries with null db', () => {
  it('getProjectStates returns []', async () => {
    const rows = await getProjectStates(null);
    assert.deepEqual(rows, []);
  });
  it('getProjectHistory returns []', async () => {
    const rows = await getProjectHistory(null, 'proj-a');
    assert.deepEqual(rows, []);
  });
  it('getRecentMetrics returns []', async () => {
    const rows = await getRecentMetrics(null);
    assert.deepEqual(rows, []);
  });
  it('getRecentSessions returns []', async () => {
    const rows = await getRecentSessions(null);
    assert.deepEqual(rows, []);
  });
});

describe('queries with real db', () => {
  let db, tmpDir;

  beforeEach(() => {
    const setup = createTestDb();
    tmpDir = setup.tmpDir;
    const { DatabaseSync } = require('node:sqlite');
    db = new DatabaseSync(setup.dbPath);
  });

  afterEach(() => {
    try { db.close(); } catch {}
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('getProjectStates returns rows ordered by timestamp desc', async () => {
    const rows = await getProjectStates(db);
    assert.equal(rows.length, 3);
    assert.equal(rows[0].project_id, 'proj-a'); // most recent first (2025-01-03)
    assert.equal(rows[0].test_passing, 6);
  });

  it('getProjectStates respects limit', async () => {
    const rows = await getProjectStates(db, 1);
    assert.equal(rows.length, 1);
  });

  it('getProjectHistory returns rows for a specific project', async () => {
    const rows = await getProjectHistory(db, 'proj-a');
    assert.equal(rows.length, 2);
    rows.forEach(r => assert.equal(r.project_id, 'proj-a'));
  });

  it('getProjectHistory respects limit', async () => {
    const rows = await getProjectHistory(db, 'proj-a', 1);
    assert.equal(rows.length, 1);
  });

  it('getRecentMetrics returns rows', async () => {
    const rows = await getRecentMetrics(db);
    assert.equal(rows.length, 3);
    assert.ok(rows[0].metric_name);
  });

  it('getRecentMetrics respects limit', async () => {
    const rows = await getRecentMetrics(db, 2);
    assert.equal(rows.length, 2);
  });

  it('getRecentSessions returns rows', async () => {
    const rows = await getRecentSessions(db);
    assert.equal(rows.length, 2);
    assert.ok(rows[0].session_file);
  });

  it('getRecentSessions respects limit', async () => {
    const rows = await getRecentSessions(db, 1);
    assert.equal(rows.length, 1);
  });
});
