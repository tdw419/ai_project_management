-- GeoForge v0.7: strategy-aware dispatch
-- Issues get a strategy (scout/surgeon/builder/fixer/refactor) that guides
-- how agents approach them. Dispatch passes the strategy to the harness.
-- Prompt templates per strategy stored in DB for customization.

-- Add strategy column to issues
ALTER TABLE issues ADD COLUMN strategy TEXT;

-- Prompt templates for each strategy
CREATE TABLE IF NOT EXISTS prompt_templates (
    id          TEXT PRIMARY KEY,
    strategy    TEXT NOT NULL UNIQUE,  -- scout, surgeon, builder, fixer, refactor
    prompt      TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Seed default templates
INSERT OR IGNORE INTO prompt_templates (id, strategy, prompt, description) VALUES
    ('tpl-scout',   'scout',   'Prioritize research and understanding before acting. Read the codebase, identify patterns, and report findings. Do NOT make changes yet.', 'Research-first approach for unknowns'),
    ('tpl-surgeon', 'surgeon', 'Make targeted, minimal edits to existing code. Understand the surrounding context before cutting. Preserve existing behavior. Small precise changes.', 'Precise edits to existing code'),
    ('tpl-builder', 'builder', 'Scaffold new modules with full test coverage. Create the structure, implement the logic, and write comprehensive tests. Think big picture.', 'New code creation with tests'),
    ('tpl-fixer',   'fixer',   'First reproduce the bug, then fix with regression tests. Verify the fix resolves the original issue without side effects.', 'Bug reproduction and fixing'),
    ('tpl-refactor','refactor','Small steps, test after every change, revert if broken. Improve code structure while preserving behavior. No functional changes.', 'Incremental restructuring');
