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

### P5 -- Production Readiness (DONE)

- [x] systemd unit file
- [x] config file (geo-forge.toml)
- [x] DB backups (SQLite WAL checkpoint)
- [x] structured JSON logging
- [x] graceful migration from Paperclip

### P6 -- Agent Orchestration (DONE)

- [x] heartbeat executor with payload
- [x] routine execution (cron -> dispatch -> capture -> record)
- [x] agent registration handshake with auto-assignment
- [x] retry & backoff on routines

### P7 -- Operational Intelligence (DONE)

- [x] P7-A: dashboard API
- [x] P7-B: alerting rules
- [x] P7-C: dependency auto-resolution
- [x] P7-D: spec document import

### P8 -- Hardening (PARTIAL)

- [x] P8-B: input validation
- [ ] P8-A: error handling audit (unwrap/expect in non-test)
- [ ] P8-C: concurrency (SQLITE_BUSY retry)
- [ ] P8-D: test coverage (80%+ on services)

---

## Active Phases

### P9 -- Outcome Verification (DONE)

Goal: stop trusting agents. Verify work actually landed.

Right now an agent marks an issue `done` and the forge believes it. No test
results, no file change tracking, no verification. An agent could submit
broken code and nobody would know until the next human checks.

- [x] **P9-A: outcomes table** -- migration 007:
      ```sql
      CREATE TABLE issue_outcomes (
          id TEXT PRIMARY KEY,
          issue_id TEXT NOT NULL REFERENCES issues(id),
          verified_at TEXT NOT NULL,
          tests_passed INTEGER DEFAULT 0,
          tests_failed INTEGER DEFAULT 0,
          tests_before INTEGER DEFAULT 0,
          tests_after INTEGER DEFAULT 0,
          files_changed TEXT NOT NULL DEFAULT '[]',  -- JSON array
          files_added TEXT NOT NULL DEFAULT '[]',
          files_removed TEXT NOT NULL DEFAULT '[]',
          import_errors TEXT NOT NULL DEFAULT '[]',
          build_success INTEGER DEFAULT 0,          -- 0 or 1
          success INTEGER NOT NULL DEFAULT 0,       -- 0 or 1
          summary TEXT NOT NULL DEFAULT '',
          raw_output TEXT,                           -- truncated test/build output
          duration_ms INTEGER DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
      );
      ```

- [x] **P9-B: verify endpoint** -- `POST /api/issues/{iid}/verify`
      The harness calls this after completing work. Body:
      ```json
      {
        "tests_passed": 782,
        "tests_failed": 0,
        "tests_before": 780,
        "tests_after": 782,
        "files_changed": ["src/gasm.rs"],
        "files_added": [],
        "files_removed": [],
        "build_success": true,
        "summary": "SUCCESS | 782 passed, 0 failed | 1 file(s) changed"
      }
      ```
      Stores the outcome. If `tests_failed > 0` or `build_success == false`,
      logs a warning. Does NOT change issue status (that's the agent's job).
      The outcome is data for the forge to reason about.

- [x] **P9-C: outcome on issue GET** -- include latest outcome in issue
      response. New field: `latest_outcome: { ... } | null`. Let any
      consumer see whether the last attempt actually worked.

- [x] **P9-D: get outcomes** -- `GET /api/issues/{iid}/outcomes` returns
      all outcome records for an issue (one per attempt). Shows whether
      the agent is making progress or thrashing.

- [x] **P9-E: outcome summary on dashboard** -- add outcome stats to
      the dashboard endpoint: verification rate, avg test delta,
      recent failures.

### P10 -- Strategy-Aware Dispatch (DONE)

Goal: the forge recommends HOW to approach a task, not just WHAT the task is.

AIPM v5 had this: SCOUT (research), SURGEON (targeted edit), BUILDER (new code),
FIXER (bugs), REFACTOR. Each strategy changes the prompt the agent receives.
Right now every issue gets the same generic prompt. Strategy-aware dispatch
means the harness can build better prompts and route to appropriate models
(local for SCOUT, cloud for BUILDER).

- [x] **P10-A: strategy field on issues** -- add `strategy` column to issues
      table (TEXT, nullable). Values: `scout`, `surgeon`, `builder`, `fixer`,
      `refactor`, null (unspecified). Migration 008.

- [x] **P10-B: strategy auto-detection** -- when creating an issue without
      an explicit strategy, infer from title/description keywords:
      - "fix", "bug", "error" -> `fixer`
      - "investigate", "analyze", "explore" -> `scout`
      - "create", "new", "build", "implement" -> `builder`
      - "refactor", "restructure" -> `refactor`
      - default: `surgeon`
      Store the detected strategy so the harness can use it.

- [x] **P10-C: strategy in dispatch response** -- when dispatch assigns an
      issue, include `strategy` in the response body. The harness reads this
      and selects the appropriate prompt template and model.

- [x] **P10-D: strategy-specific prompt templates** -- store prompt templates
      per strategy in a new `prompt_templates` table or as config:
      - SCOUT: "Prioritize research and understanding before acting."
      - SURGEON: "Make targeted, minimal edits to existing code."
      - BUILDER: "Scaffold new modules with full test coverage."
      - FIXER: "First reproduce the bug, then fix with regression tests."
      - REFACTOR: "Small steps, test after every change, revert if broken."
      The harness requests the template via `GET /api/strategies/{name}/prompt`.

- [x] **P10-E: retry strategy pivot** -- when an issue fails and gets
      reattempted, automatically shift strategy. Non-diagnostic strategies
      fall back to SCOUT on retry (investigate why it failed). Track the
      strategy used per attempt in the outcome record.

### P11 -- Self-Improvement Loop

Goal: the forge learns from its history and gets better over time.

AIPM v5 had proposal scoring and strategy learnings. Every completed change
got scored on success rate, test delta, duration. Patterns emerged: which
proposal types work, which modules are hard, whether things are improving.
These learnings fed back into the strategist prompts.

Geo-forge has the activity log and (after P9) outcome data. This phase closes
the loop by aggregating that data into actionable learnings.

- [ ] **P11-A: company learnings endpoint** --
      `GET /api/companies/{cid}/learnings` aggregates outcome history:
      - Overall success rate (outcomes where success=true / total outcomes)
      - Per-strategy success rate (scout vs surgeon vs builder vs fixer)
      - Net test delta across all completed issues
      - Average issue duration (started_at -> completed_at)
      - Recent trend: improving / declining / stable (compare last 10 vs previous 10)

- [ ] **P11-B: module difficulty tracking** -- aggregate outcomes by files
      changed. Modules where agents frequently fail get flagged as "hard".
      Modules where agents succeed get flagged as "easy". Return in the
      learnings endpoint so the strategist can adapt.

- [ ] **P11-C: learnings in dispatch response** -- when dispatch assigns
      an issue, include relevant learnings: "this module has 60% failure
      rate, consider smaller steps" or "similar issues took 45min avg".
      The harness uses this to set expectations and adjust approach.

- [ ] **P11-D: recommendations engine** -- from the learnings data, generate
      actionable recommendations:
      - "Stop proposing refactors to module X -- 3 failures in a row"
      - "Fixer strategy has 90% success -- keep using it for bug issues"
      - "Overall success rate declining -- propose smaller changes"
      Exposed via the learnings endpoint as a `recommendations` array.

- [ ] **P11-E: outcome-triggered learnings update** -- when a new outcome
      is recorded (P9-B), recompute learnings in the background. The
      learnings endpoint always returns fresh data.

### P12 -- Multi-Agent Coordination

Goal: multiple agents working in concert, not just dispatched independently.

- [ ] **P12-A: atomic work claiming** -- `checkout` endpoint uses optimistic
      locking. Two agents can't grab the same issue. Returns `409 Conflict`
      if already claimed. The `expected_statuses` field already does this --
      verify it works under concurrent load.

- [ ] **P12-B: structured agent comments** -- comments get a `comment_type`
      field: `progress`, `blocker`, `handoff`, `review_note`. Machine-readable
      comments that other agents can parse. "Blocked by GEO-42" as a typed
      comment, not free text.

- [ ] **P12-C: batch dispatch** -- `POST /api/companies/{cid}/dispatch/batch`
      assigns N issues to N idle agents simultaneously. For parallel work
      streams. Returns which agent got which issue.

- [ ] **P12-D: capacity limits** -- per-agent workload cap. Don't assign
      15 issues to one agent. Configurable `max_assigned` on agents
      (default 5). Dispatch skips agents at capacity.

### P13 -- Workspace Integration

Goal: agents read and write the real world through Google Workspace.

- [ ] **P13-A: install and authenticate gws CLI**
- [ ] **P13-B: skill ingestion** -- 95 gws-* skills available to agents
- [ ] **P13-C: email-to-issue bridge** -- Gmail poll -> auto-create issues
- [ ] **P13-D: dashboard to Sheet** -- daily routine writes metrics to Google Sheet
- [ ] **P13-E: calendar-driven scheduling** -- due dates from calendar events

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

---

## Phase Dependency Graph

```
P8 (hardening) -- independent, do anytime
P9 (outcomes) -----> P10 (strategy) -----> P11 (learnings)
P12 (multi-agent) -- independent, do anytime after P9
P13 (workspace) ---- independent, do anytime
```

P9 is the critical path. Without outcome verification, strategy and learnings
have no data to reason about. Do P9 first, then P10, then P11. P8, P12, and
P13 can happen in parallel with any of these.
