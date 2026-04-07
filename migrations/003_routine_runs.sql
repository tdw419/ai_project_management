-- GeoForge v0.2: routine_runs for tracking routine execution history
CREATE TABLE IF NOT EXISTS routine_runs (
    id              TEXT PRIMARY KEY,
    routine_id      TEXT NOT NULL REFERENCES routines(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    company_id      TEXT NOT NULL REFERENCES companies(id),
    issue_id        TEXT REFERENCES issues(id),
    triggered_by    TEXT NOT NULL DEFAULT 'cron',
    status          TEXT NOT NULL DEFAULT 'running',
    output          TEXT,
    started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at    TEXT,
    duration_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_routine_runs_routine ON routine_runs(routine_id);
CREATE INDEX IF NOT EXISTS idx_routine_runs_company ON routine_runs(company_id);
