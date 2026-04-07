-- GeoForge v0.3: retry & backoff for routines
-- Track consecutive failures and configure retry behavior

-- Add retry config to routines
ALTER TABLE routines ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 3;
ALTER TABLE routines ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0;
ALTER TABLE routines ADD COLUMN retry_interval_secs INTEGER NOT NULL DEFAULT 300;
ALTER TABLE routines ADD COLUMN next_retry_at TEXT;
