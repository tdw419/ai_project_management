-- GeoForge v0.6: outcome verification
-- After an agent completes work, the harness calls verify with test results and file changes.
-- This is the foundation for P10 (strategy) and P11 (learnings).

CREATE TABLE IF NOT EXISTS issue_outcomes (
    id              TEXT PRIMARY KEY,
    issue_id        TEXT NOT NULL REFERENCES issues(id),
    verified_at     TEXT NOT NULL,
    tests_passed    INTEGER NOT NULL DEFAULT 0,
    tests_failed    INTEGER NOT NULL DEFAULT 0,
    tests_before    INTEGER NOT NULL DEFAULT 0,
    tests_after     INTEGER NOT NULL DEFAULT 0,
    files_changed   TEXT NOT NULL DEFAULT '[]',   -- JSON array of file paths
    files_added     TEXT NOT NULL DEFAULT '[]',   -- JSON array of file paths
    files_removed   TEXT NOT NULL DEFAULT '[]',   -- JSON array of file paths
    import_errors   TEXT NOT NULL DEFAULT '[]',   -- JSON array of error strings
    build_success   INTEGER NOT NULL DEFAULT 0,   -- 0 or 1
    success         INTEGER NOT NULL DEFAULT 0,   -- 0 or 1
    summary         TEXT NOT NULL DEFAULT '',
    raw_output      TEXT,                          -- truncated test/build output (nullable)
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_outcomes_issue_id ON issue_outcomes(issue_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_success ON issue_outcomes(success);
CREATE INDEX IF NOT EXISTS idx_outcomes_created_at ON issue_outcomes(created_at);
