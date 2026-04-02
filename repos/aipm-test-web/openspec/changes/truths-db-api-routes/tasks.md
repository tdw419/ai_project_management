# Tasks: Truths DB REST API with Modular Route Structure

## 1. Phase 1: Database Access Layer
- [x] 1.1 Create src/db/truths.js -- exports getDb(path) that opens truths.db with node:sqlite (DatabaseSync, not node:sqlite3 -- Node 24 uses node:sqlite), returns null on missing/corrupt file (no throw), and a close() function. Default path reads from TRUTHS_DB_PATH env var or falls back to /home/jericho/zion/projects/aipm/data/truths.db
- [x] 1.2 Create src/db/queries.js -- exports functions: getProjectStates(db, limit=20), getProjectHistory(db, projectId, limit=10), getRecentMetrics(db, limit=50), getRecentSessions(db, limit=20). Each returns [] on null db. Uses parameterized queries only.

## 2. Phase 2: Middleware and Error Handling
- [x] 2.1 Create src/middleware/error-handler.js -- Express error handler that catches db errors, returns 503 with {error: 'service unavailable', detail: message} for sqlite errors, 500 for unexpected errors. Logs to stderr.
- [x] 2.2 Create src/middleware/request-logger.js -- Lightweight request logger that logs method, path, status, and duration in ms to stdout.

## 3. Phase 3: Route Modules
- [x] 3.1 Create src/routes/health.js -- GET /health returns {status:'ok', db: boolean indicating truths.db connectivity, uptime: process.uptime()}. Tests db with a trivial SELECT 1 query.
- [x] 3.2 Create src/routes/projects.js -- GET /api/projects returns list from project_state. GET /api/projects/:id/history returns snapshots for a specific project_id. Both return 503 if db is null.
- [x] 3.3 Create src/routes/metrics.js -- GET /api/metrics returns recent rows from metrics table. Supports ?name= filter query param.
- [x] 3.4 Create src/routes/sessions.js -- GET /api/sessions returns recent session_index rows. Supports ?project= filter query param.

## 4. Phase 4: App Bootstrap
- [x] 4.1 Refactor index.js to use express.json() parser, mount routes from src/routes/*, attach error-handler and request-logger middleware. Keep port configurable via PORT env var (default 3000). Export app for testing (don't listen on import).
- [x] 4.2 Update package.json scripts: test becomes 'node --test test/**/*.test.js', add start script as 'node index.js'.

## 5. Phase 5: Test Suite
- [ ] 5.1 Create test/health.test.js -- tests GET /health returns 200 with correct shape, handles missing db gracefully (mock getDb to return null, expect db:false in response).
- [ ] 5.2 Create test/projects.test.js -- tests GET /api/projects returns array, GET /api/projects/:id/history returns array, both return 503 when db is null.
- [ ] 5.3 Create test/error-handling.test.js -- tests that malformed requests get proper JSON error responses, not HTML stack traces.
- [ ] 5.4 Create test/setup.js -- helper that creates a fresh app instance with optional in-memory sqlite db for isolated testing.
