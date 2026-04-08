-- V2-P1: Webhooks & Events system
-- Conway-inspired event-driven architecture: push, not pull.

-- Internal event log. Every state change emits an event here.
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    event_type TEXT NOT NULL,       -- e.g. "issue.created", "issue.status_changed", "agent.status_changed"
    payload TEXT NOT NULL,          -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_events_company_type ON events(company_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

-- Webhook subscriptions: external services (or harness workers) register to receive events.
CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    event_type TEXT NOT NULL,       -- glob pattern: "issue.*", "agent.*", "issue.created", etc.
    target_url TEXT NOT NULL,       -- URL to POST to
    secret TEXT NOT NULL,           -- HMAC-SHA256 signing secret
    active INTEGER NOT NULL DEFAULT 1,
    headers TEXT DEFAULT '{}',      -- JSON: extra headers to send
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_webhooks_company ON webhooks(company_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_active ON webhooks(active);

-- Delivery log: tracks every webhook delivery attempt.
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    payload TEXT NOT NULL,          -- JSON: the full payload sent
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, delivered, failed, retrying
    response_code INTEGER,
    response_body TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    last_attempt_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (webhook_id) REFERENCES webhooks(id),
    FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE INDEX IF NOT EXISTS idx_deliveries_status ON webhook_deliveries(status);
CREATE INDEX IF NOT EXISTS idx_deliveries_next_retry ON webhook_deliveries(next_retry_at);
