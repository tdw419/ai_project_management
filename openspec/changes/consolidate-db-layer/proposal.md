## Why

AIPM uses 4 separate SQLite databases (truths.db, queue.db, projects.db, aipm.db) with raw sqlite3 calls scattered across modules. No ORM, no migrations, no schema versioning. This causes:
- Schema drift between databases
- No transactional safety across databases
- Hard to test (each module manages its own connections)
- Duplicated connection boilerplate (connect, close, error handling)

## What Changes

- Consolidate into a single `data/aipm.db` with schema-managed tables
- Create a `aipm/db.py` module with shared connection management, schema versioning, and migration support
- Migrate all modules to use the shared database layer

## Success Criteria

- Single SQLite database file
- All tables have explicit schemas with version tracking
- Migration path exists for existing data
- All raw sqlite3 calls go through db.py

## Impact

- **New**: `aipm/db.py` (connection pool, schema management, migrations)
- **Modified**: `state.py`, `prompt_log.py`, `metrics.py`, `session_historian.py`, `issue_queue.py`, `watchdog.py`
- **Removed**: `data/truths.db`, `data/queue.db`, `data/projects.db`
- **Risk**: Medium -- data migration must be lossless
