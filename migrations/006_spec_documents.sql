-- GeoForge v0.5: spec document ingestion and spec-to-issue mapping
-- OpenSpec documents contain change sections that can be imported as issues

CREATE TABLE IF NOT EXISTS spec_documents (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    title           TEXT NOT NULL,
    raw_content     TEXT NOT NULL,
    parsed_changes  TEXT NOT NULL DEFAULT '[]',  -- JSON array of parsed change sections
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft, imported, partial
    change_count    INTEGER NOT NULL DEFAULT 0,
    imported_count  INTEGER NOT NULL DEFAULT 0,
    project_id      TEXT REFERENCES projects(id),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS spec_issues (
    id              TEXT PRIMARY KEY,
    spec_id         TEXT NOT NULL REFERENCES spec_documents(id),
    issue_id        TEXT NOT NULL REFERENCES issues(id),
    change_index    INTEGER NOT NULL,  -- which change section in the spec (0-based)
    change_title    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
