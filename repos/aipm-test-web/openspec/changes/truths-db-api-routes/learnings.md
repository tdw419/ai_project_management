# Learnings: SEC-1 Database Access Layer

## What worked
- Testing against real in-memory sqlite files (via tmpdir) instead of mocks -- catches real API surface issues.
- Checking `node:sqlite` availability before starting; the spec said `node:sqlite3` which doesn't exist on Node 24. Correcting this in the spec saves future agents from the same error.

## What didn't
- The original spec referenced `node:sqlite3` which is wrong for Node 24. The correct module is `node:sqlite` with `DatabaseSync` class. Updated proposal.md and tasks.md to reflect this.

## What would I do differently
- The query functions are synchronous (node:sqlite is sync), so returning plain arrays is the right call. No need for async/await in the query layer, but tests used `await` anyway -- harmless but slightly misleading. Left as-is since it works fine.

---

# Learnings: SEC-2 Middleware and Error Handling

## What worked
- Using EventEmitter-based mock for `res` in request-logger tests -- lets us emit 'finish' to trigger the log, which is how Express actually works.
- Swapping process.stderr/stdout via Object.defineProperty to capture log output in tests. Simple and effective for unit-testing middleware without supertest.
- Combining both middleware tests into a single `test/middleware.test.js` file -- keeps the test count low and avoids needing another dependency.

## What didn't
- Initially wrote a non-EventEmitter mock for res, then realized request-logger needs `res.on('finish', ...)`. Had to rewrite the mock. Should have started with EventEmitter mock from the start since Express response objects extend ServerResponse (an EventEmitter).

## What would I do differently
- The request-logger test uses `setImmediate` to let the finish handler flush to the stream. Works but slightly fragile. Could also use a callback-based approach, but this is fine for a unit test.

---

# Learnings: SEC-3 Route Modules

## What worked
- Using factory functions (e.g., `createHealthRouter(getDb)`) instead of importing getDb directly. This makes routes testable without touching the real filesystem -- the caller injects the db getter.
- Leveraging the existing query layer for filtering (getRecentMetrics/getRecentSessions return arrays, route handlers filter in-memory for ?name= and ?project= params). Keeps the query layer simple and the routes thin.
- Express Router pattern with `try/catch + next(err)` ensures all db errors flow to the centralized error-handler middleware from Phase 2.

## What didn't
- Nothing notable -- the pattern was well-established by Phases 1 and 2.

## What would I do differently
- For large datasets, in-memory filtering by query param would be inefficient. If truths.db grows significantly, add WHERE-clause variants to the query layer. Fine for now.

## pattern

- **[pattern]** (from SEC-3) [added] src/routes/projects.js

- **[pattern]** (from SEC-3) [added] src/routes/health.js

- **[pattern]** (from SEC-3) [added] src/routes/sessions.js

- **[pattern]** (from SEC-3) [added] src/routes/metrics.js

- **[pattern]** (from SEC-3) [modified] openspec/changes/truths-db-api-routes/learnings.md

## discovery

- **[discovery]** (from SEC-3) Agent strategy: created 4 files, modified 2 files, added tests

---

# Learnings: SEC-4 App Bootstrap

## What worked
- Factory function pattern from SEC-3 made wiring trivial -- each router takes getDb, index.js just passes it through. Zero coupling between app bootstrap and route internals.
- `require.main === module` guard is the idiomatic way to export app for testing while still listening when run directly. Clean.
- Express 5 handles middleware ordering naturally: requestLogger first, routes, then errorHandler last.

## What didn't
- Nothing -- this was a 2-file change with clear requirements.

## What would I do differently
- Could consider a `createApp(getDb)` factory for even better testability (inject the db getter at app creation), but the current approach where index.js calls `getDb` directly and passes it to each router is fine for this project's scale.

- **[pattern]** (from SEC-4) [modified] package.json

- **[pattern]** (from SEC-4) [modified] index.js

- **[pattern]** (from SEC-4) [modified] openspec/changes/truths-db-api-routes/learnings.md

- **[pattern]** (from SEC-4) [modified] openspec/changes/truths-db-api-routes/tasks.md

- **[pattern]** (from SEC-4) [added] test/app-bootstrap.test.js

- **[discovery]** (from SEC-4) Agent strategy: created 1 file, modified 4 files, refactored, added tests, fix attempt
