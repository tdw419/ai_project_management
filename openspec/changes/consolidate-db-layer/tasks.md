## 1. Database Abstraction Layer

- [ ] 1.1 Create `aipm/db.py` with `get_connection()`, `init_schema()`, `run_migration()`
- [ ] 1.2 Define all table schemas in db.py with explicit CREATE TABLE statements
- [ ] 1.3 Add schema version tracking table (`_meta` with version column)
- [ ] 1.4 Add migration framework (upgrade/downgrade functions per version)

## 2. Migrate Existing Tables

- [ ] 2.1 Move project_state table from truths.db to unified schema
- [ ] 2.2 Move prompt_log table from truths.db to unified schema
- [ ] 2.3 Move session_index table from truths.db to unified schema
- [ ] 2.4 Move issue_cooldown table from truths.db to unified schema
- [ ] 2.5 Move metrics table from truths.db to unified schema
- [ ] 2.6 Move queue table from queue.db to unified schema (or drop if unused)

## 3. Update All Modules

- [ ] 3.1 Update state.py to use db.py instead of raw sqlite3
- [ ] 3.2 Update prompt_log.py to use db.py
- [ ] 3.3 Update metrics.py to use db.py
- [ ] 3.4 Update session_historian.py to use db.py
- [ ] 3.5 Update issue_queue.py to use db.py
- [ ] 3.6 Update watchdog.py to use db.py

## 4. Data Migration

- [ ] 4.1 Write migration script that copies data from old DBs to new unified DB
- [ ] 4.2 Backup old DB files before migration
- [ ] 4.3 Test migration on existing data directory

## 5. Verification

- [ ] 5.1 Only `data/aipm.db` exists after migration
- [ ] 5.2 `grep -r "sqlite3.connect" aipm/` only appears in db.py
- [ ] 5.3 All existing tests pass
- [ ] 5.4 Manual test: `main.py run-once` works with new DB
