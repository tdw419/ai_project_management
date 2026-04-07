-- GeoForge initial schema
-- Replaces Paperclip's 61 tables with the 10 we actually need.

-- Companies (top-level container)
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    issue_prefix TEXT NOT NULL DEFAULT 'GEO',
    issue_counter INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Agents (AI workers)
CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'general',
    status          TEXT NOT NULL DEFAULT 'idle',
    adapter_type    TEXT NOT NULL DEFAULT 'hermes_local',
    adapter_config  TEXT NOT NULL DEFAULT '{}',
    runtime_config  TEXT NOT NULL DEFAULT '{}',
    reports_to      TEXT REFERENCES agents(id),
    permissions     TEXT NOT NULL DEFAULT '{}',
    last_heartbeat  TEXT,
    paused_at       TEXT,
    error_message   TEXT,
    health_status   TEXT NOT NULL DEFAULT 'unknown',
    health_check_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agents_company ON agents(company_id);
CREATE INDEX IF NOT EXISTS idx_agents_company_status ON agents(company_id, status);

-- Projects (group issues)
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'in_progress',
    color       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_projects_company ON projects(company_id);

-- Goals (milestones)
CREATE TABLE IF NOT EXISTS goals (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    title       TEXT NOT NULL,
    description TEXT,
    level       TEXT NOT NULL DEFAULT 'task',
    status      TEXT NOT NULL DEFAULT 'planned',
    parent_id   TEXT REFERENCES goals(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_goals_company ON goals(company_id);

-- Labels
CREATE TABLE IF NOT EXISTS labels (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    name        TEXT NOT NULL,
    color       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_labels_company ON labels(company_id);

-- Issues (work items)
CREATE TABLE IF NOT EXISTS issues (
    id               TEXT PRIMARY KEY,
    company_id       TEXT NOT NULL REFERENCES companies(id),
    project_id       TEXT REFERENCES projects(id),
    parent_id        TEXT REFERENCES issues(id),
    title            TEXT NOT NULL,
    description      TEXT,
    status           TEXT NOT NULL DEFAULT 'backlog',
    priority         TEXT NOT NULL DEFAULT 'medium',
    assignee_agent_id TEXT REFERENCES agents(id),
    identifier       TEXT UNIQUE,
    issue_number     INTEGER,
    origin_kind      TEXT NOT NULL DEFAULT 'manual',
    origin_id        TEXT,
    blocked_by       TEXT DEFAULT '[]',
    started_at       TEXT,
    completed_at     TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN ('backlog', 'todo', 'in_progress', 'in_review', 'done', 'cancelled')),
    CHECK (priority IN ('critical', 'high', 'medium', 'low'))
);
CREATE INDEX IF NOT EXISTS idx_issues_company ON issues(company_id);
CREATE INDEX IF NOT EXISTS idx_issues_company_status ON issues(company_id, status);
CREATE INDEX IF NOT EXISTS idx_issues_assignee ON issues(company_id, assignee_agent_id, status);
CREATE INDEX IF NOT EXISTS idx_issues_identifier ON issues(identifier);

-- Issue labels (join table)
CREATE TABLE IF NOT EXISTS issue_labels (
    issue_id    TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    label_id    TEXT NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
    PRIMARY KEY (issue_id, label_id)
);

-- Issue comments
CREATE TABLE IF NOT EXISTS issue_comments (
    id              TEXT PRIMARY KEY,
    issue_id        TEXT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    body            TEXT NOT NULL,
    author_agent_id TEXT REFERENCES agents(id),
    author_user_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comments_issue ON issue_comments(issue_id);

-- Routines (scheduled agent heartbeats)
CREATE TABLE IF NOT EXISTS routines (
    id                TEXT PRIMARY KEY,
    company_id        TEXT NOT NULL REFERENCES companies(id),
    project_id        TEXT REFERENCES projects(id),
    title             TEXT NOT NULL,
    description       TEXT,
    assignee_agent_id TEXT NOT NULL REFERENCES agents(id),
    cron_expression   TEXT,
    status            TEXT NOT NULL DEFAULT 'active',
    concurrency       TEXT NOT NULL DEFAULT 'skip_if_active',
    last_triggered_at TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_routines_company ON routines(company_id);

-- Activity log
CREATE TABLE IF NOT EXISTS activity_log (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    actor_type  TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    details     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_activity_company ON activity_log(company_id);
CREATE INDEX IF NOT EXISTS idx_activity_entity ON activity_log(entity_type, entity_id);
