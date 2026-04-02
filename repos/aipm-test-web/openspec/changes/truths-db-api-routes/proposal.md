# Proposal: Truths DB REST API with Modular Route Structure

## Summary
The app is currently a single-file Express skeleton with one health-check route and no real functionality. Previous AIPM sessions failed trying to add truths.db access and route modules (errors: 'graceful error handling if truths.db doesn't exist' and 'Create src/routes/projects.js'). This change restructures the app into a proper modular layout (src/routes/, src/middleware/, src/db/) and adds REST endpoints that query the existing truths.db -- /api/projects for project_state, /api/projects/:id/history for recent state snapshots, /api/metrics for aggregated metrics, and /api/sessions for session_index data. Each route has graceful 503 handling when truths.db is missing or corrupt, directly addressing the past failure. Adds a real test suite using node:test (built-in, zero new deps) so AIPM's test runner gets meaningful signal instead of just syntax checking.

## Dependencies
truths.db already exists at /home/jericho/zion/projects/aipm/data/truths.db with project_state, metrics, and session_index tables. No new npm dependencies needed -- node:sqlite (DatabaseSync) is available in Node 24+ (NOT node:sqlite3 -- that module doesn't exist) and node:test is built-in.

## Success Criteria
- All tasks complete and tests pass