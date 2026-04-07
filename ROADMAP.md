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

### P5 -- Production Readiness (DONE)

Goal: run GeoForge as a systemd service, replace Paperclip for real.

- [x] **P5-A: systemd unit file** -- `geo-forge.service` with auto-restart,
      journal logging, env file for config
- [x] **P5-B: config file** -- `geo-forge.toml` or env-based config for
      DB path, port, health thresholds, scheduler interval, rate limits.
      Stop using raw env vars scattered everywhere.
- [x] **P5-C: DB backups** -- SQLite WAL checkpoint + periodic copy.
      One cron job, one line.
- [x] **P5-D: logging** -- structured JSON logs (tracing-subscriber with
      json formatter). Pipe to journalctl, done.
- [x] **P5-E: graceful migration** -- dry-run migration against live
      Paperclip data, verify counts, then cutover. Keep Paperclip on
      port 3100 as read-only fallback for 48h.

### P6 -- Agent Orchestration (DONE)

Goal: agents actually run through GeoForge, not just tracked.

- [x] **P6-A: heartbeat executor** -- heartbeat endpoint accepts payload
      with `current_issue_id`, `progress_notes`, `capabilities`. Logs to
      activity. Health monitor runs as background task.
- [x] **P6-B: routine execution** -- scheduler fires routines end-to-end:
      cron evaluation -> issue finding -> agent invocation -> stdout/stderr
      capture -> routine_runs recording + invocations recording. New
      `GET /api/routines/{rid}/runs` endpoint for run history.
- [x] **P6-C: agent lifecycle** -- registration handshake endpoint
      `POST /api/companies/{cid}/agents/register` with capabilities manifest.
      Auto-assigns up to 5 backlogged todo issues. Re-registration reactivates
      paused/error agents.
- [x] **P6-D: retry & backoff** -- `max_retries` (default 3) and
      `retry_interval_secs` (default 300) on routines. Exponential backoff
      on failure. Auto-pauses agent + deactivates routine after max retries.

**Current: 28 src files, ~3700 LOC, 47 tests, 13 tables, 39+ endpoints.**

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

### P10 -- Workspace Integration

Goal: agents read and write the real world through Google Workspace.

The `gws` CLI (googleworkspace/cli) is a Rust binary that wraps all Google
Workspace APIs with structured JSON output.  It ships 95 agent-ready skills
in OpenClaw format.  This phase makes it a first-class forge capability.

- [ ] **P10-A: install and authenticate** -- build `gws` from
      ~/zion/projects/ai_harness/ai_harness/cli-main, run `gws auth setup`
      + `gws auth login`.  Verify with `gws drive files list --fields "files(id,name)"`.
- [ ] **P10-B: skill ingestion** -- copy the 95 `gws-*` and `recipe-*` skills
      from cli-main/skills/ into the forge agent's skill directory.  Agents
      discover `gws` commands through their skill set, no forge code changes.
- [ ] **P10-C: email-to-issue bridge** -- a forge routine that polls Gmail
      via `gws gmail users messages list`, parses new messages matching a
      pattern (subject tag, label, or sender), and creates issues
      automatically.  The inverse of "agent posts comment -> notification".
- [ ] **P10-D: dashboard to Sheet** -- a forge routine that runs daily,
      calls the dashboard API, and writes throughput / bottleneck /
      utilization data into a Google Sheet.  Stakeholders see live project
      health without touching the forge.
- [ ] **P10-E: calendar-driven scheduling** -- agents check Google Calendar
      for review windows, standups, or deadlines.  Issues get due-dates from
      calendar events.  An agent that finishes early can propose a meeting
      via `gws calendar events insert`.

**Why this phase exists:**  The forge is a closed loop right now -- issues
go in, agents work on them, comments come out.  Workspace integration opens
the loop: email creates work, spreadsheets report status, calendar drives
cadence.  It's the difference between a tool and a team member.

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
