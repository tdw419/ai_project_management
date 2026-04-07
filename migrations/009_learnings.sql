-- GeoForge v0.8: Self-Improvement Loop (P11)
-- Module difficulty tracking: aggregate outcome history by file path.
-- This gets recomputed on every new outcome (P11-E).
-- The learnings endpoint (P11-A) reads from here + live SQL aggregates.

CREATE TABLE IF NOT EXISTS module_difficulty (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    file_path   TEXT NOT NULL,
    total_attempts INTEGER NOT NULL DEFAULT 0,
    failures    INTEGER NOT NULL DEFAULT 0,
    successes   INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms REAL NOT NULL DEFAULT 0.0,
    last_attempt_at TEXT,
    difficulty  TEXT NOT NULL DEFAULT 'unknown',  -- 'easy', 'medium', 'hard', 'unknown'
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(company_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_module_difficulty_company ON module_difficulty(company_id);
CREATE INDEX IF NOT EXISTS idx_module_difficulty_difficulty ON module_difficulty(difficulty);
