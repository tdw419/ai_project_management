-- GeoForge v0.4: alert rules for operational intelligence
-- Configurable rules that evaluate conditions and fire activity_log entries

CREATE TABLE IF NOT EXISTS alert_rules (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    name            TEXT NOT NULL,
    rule_type       TEXT NOT NULL,     -- 'agent_dead', 'issue_blocked', 'no_activity', 'custom'
    threshold_mins  INTEGER NOT NULL,  -- how long before alerting
    enabled         INTEGER NOT NULL DEFAULT 1,
    webhook_url     TEXT,              -- optional webhook to POST to
    last_fired_at   TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
