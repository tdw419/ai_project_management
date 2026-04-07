# GeoForge Roadmap

> Paperclip replacement. Rust/Axum/SQLite. Port 3101.

## Completed

### P1 -- Foundation (DONE)
Scaffold, schema, migrations, basic CRUD routes.

### P2 -- Core Services (DONE)
State machine, dispatch, dependency tracking, health monitor scaffolding,
rate limiting, CORS, structured metrics, graceful shutdown.

### P3 -- Polish & Features (DONE)
Agent heartbeat, scheduler loop, executor (hermes_local adapter),
agent CRUD (update/delete), issue soft-delete, activity logging,
routine runs table, issue filtering.

### P4 -- Testing & Migration (DONE)
27 integration tests (in-memory SQLite + full Axum router).
Bug found: blockers `SELECT` was missing columns.
Migration script (`migrate_from_paperclip.py`).
20 unit tests.

**Current: 26 src files, 4134 LOC, 47 tests, 12 tables, 37+ endpoints.**

---

## Next Phases

### P5 -- Production Readiness

Goal: run GeoForge as a systemd service, replace Paperclip for real.

- [ ] **P5-A: systemd unit file** -- `geo-forge.service` with auto-restart,
      journal logging, env file for config
- [ ] **P5-B: config file** -- `geo-forge.toml` or env-based config for
      DB path, port, health thresholds, scheduler interval, rate limits.
      Stop using raw env vars scattered everywhere.
- [ ] **P5-C: DB backups** -- SQLite WAL checkpoint + periodic copy.
      One cron job, one line.
- [ ] **P5-D: logging** -- structured JSON logs (tracing-subscriber with
      json formatter). Pipe to journalctl, done.
- [ ] **P5-E: graceful migration** -- dry-run migration against live
      Paperclip data, verify counts, then cutover. Keep Paperclip on
      port 3100 as read-only fallback for 48h.

### P6 -- Agent Orchestration (Real)

Goal: agents actually run through GeoForge, not just tracked.

- [ ] **P6-A: heartbeat executor** -- agents POST heartbeat with status
      payload (current issue, progress notes). GeoForge updates
      health_status + last_heartbeat. Wire the existing `health_monitor`
      background task.
- [ ] **P6-B: routine execution** -- when scheduler fires a routine,
      record the run in `routine_runs`, invoke the agent, capture
      stdout/stderr + exit code, log to activity. Currently executor
      exists but isn't wired end-to-end.
- [ ] **P6-C: agent lifecycle** -- agent registration with capabilities
      manifest. Startup handshake: agent announces itself, GeoForge
      assigns backlogged work or marks idle.
- [ ] **P6-D: retry & backoff** -- failed invocations retry with
      exponential backoff. Configurable max retries per routine.
      Dead agents get auto-paused after N failures.

### P7 -- Operational Intelligence

Goal: GeoForge tells you what's happening, not just records it.

- [ ] **P7-A: dashboard API** -- `/api/companies/:cid/dashboard` returns
      real metrics: issue throughput (created/resolved per day), agent
      utilization (% time active), bottleneck detection (issues stuck
      in_review >24h), blocker chains.
- [ ] **P7-B: alerting** -- configurable rules: "agent dead >30min",
      "issue blocked >48h", "no activity in 24h". Fire as activity_log
      entries + optional webhook.
- [ ] **P7-C: dependency auto-resolution** -- when issue moves to
      `done`, check if any blocked issues are now fully unblocked.
      Auto-promote from `backlog` to `todo`. Log the promotion.
- [ ] **P7-D: spec module** -- read OpenSpec documents, create issues
      from specs, track spec-to-issue mapping. The missing link between
      Geometry OS specs and GeoForge work items.

### P8 -- Hardening

Goal: zero surprises in production.

- [ ] **P8-A: error handling audit** -- every `unwrap()` and `expect()`
      in non-test code gets proper error propagation. No panics in prod.
- [ ] **P8-B: input validation** -- request body validation with clear
      error messages. Reject garbage early. Length limits on strings,
      enum validation on status fields.
- [ ] **P8-C: concurrency** -- SQLite is single-writer. Verify all
      write paths handle `SQLITE_BUSY` with retry. Test under concurrent
      load (even just 10 concurrent requests).
- [ ] **P8-D: test coverage** -- target 80%+ coverage on services.
      Add property-based tests for state machine. Add chaos tests
      (random concurrent reads/writes).

### P9 -- Multi-Agent Coordination

Goal: multiple agents working in concert, not just dispatched independently.

- [ ] **P9-A: work claiming** -- atomic checkout with optimistic locking.
      Two agents can't grab the same issue. `checkout` endpoint returns
      `409 Conflict` if already claimed.
- [ ] **P9-B: agent communication** -- agents can leave structured
      comments for other agents (not just free text). "Blocked by GEO-42"
      as a machine-readable comment type.
- [ ] **P9-C: pipeline workflows** -- define issue pipelines:
      "spec review -> implementation -> QA -> merge". Agents auto-assign
      based on role + pipeline stage.
- [ ] **P9-D: capacity planning** -- agent workload limits. Don't assign
      15 issues to one agent. Queue management with per-agent limits.

---

## Not Planned (Deliberately)

These are things Paperclip has that we explicitly don't need:

- Auth system (local_trusted mode forever)
- Plugins/approvals/sidebar badges
- Workspaces/org charts
- Budget/cost tracking (keep it simple)
- Secrets management (agents handle their own)
- Feedback/survey system
- Docker/Postgres dependency
