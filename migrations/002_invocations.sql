-- Invocations (execution history)
CREATE TABLE IF NOT EXISTS invocations (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    company_id      TEXT NOT NULL REFERENCES companies(id),
    issue_id        TEXT REFERENCES issues(id),
    routine_id      TEXT REFERENCES routines(id),
    started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at    TEXT,
    exit_code       INTEGER,
    success         INTEGER NOT NULL DEFAULT 0,
    output_truncated TEXT,
    triggered_by    TEXT NOT NULL CHECK(triggered_by IN ('wakeup', 'invoke', 'dispatch', 'routine', 'manual')),
    duration_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_invocations_agent ON invocations(agent_id);
CREATE INDEX IF NOT EXISTS idx_invocations_company ON invocations(company_id);
CREATE INDEX IF NOT EXISTS idx_invocations_company_agent ON invocations(company_id, agent_id);
