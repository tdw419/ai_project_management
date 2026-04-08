-- V2-P3: Human Injection Channel
-- Allows humans to inject guidance messages into a running agent's context.

CREATE TABLE IF NOT EXISTS agent_injections (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    message TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'normal',  -- 'low', 'normal', 'high', 'urgent'
    source TEXT DEFAULT 'human',     -- 'human', 'system', 'overseer'
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    read_at TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX idx_injections_agent ON agent_injections(agent_id);
CREATE INDEX idx_injections_read ON agent_injections(agent_id, read);
