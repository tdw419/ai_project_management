# GeoForge -- Geometry OS Agent Orchestrator

> The thing that forges Geometry OS. Replaces Paperclip as the autonomous
> agent orchestration layer.

## Why

Paperclip works but we've outgrown it. We spend sessions working around its
limitations (duplicate issues, fragile idempotency, no health checks, rigid
dispatch). An AI-powered OS should orchestrate its own agents -- that's the
product, not external infrastructure you patched with pnpm.

## What We Actually Use From Paperclip

Out of Paperclip's 61 tables, 70 services, 14K lines of routes, we use:

| Feature | Endpoints | Tables |
|---------|-----------|--------|
| Companies | list, dashboard | companies |
| Agents | list, get, wakeup, update | agents, agent_api_keys, heartbeat_runs |
| Issues | list, get, create, update, checkout, comments | issues, issue_comments, issue_labels, labels |
| Projects | list, get | projects |
| Goals | list | goals |
| Routines | CEO roadmap sync, daily report | routines, routine_triggers, routine_runs |
| Activity | implicit (logging) | activity_log, cost_events |

That's ~10 tables, ~15 endpoints. The other 51 tables and 85% of the API
(approvals, plugins, workspaces, secrets, budgets, feedback, org charts,
auth, sidebar badges) are unused.

## Architecture

```
┌─────────────────────────────────────────────┐
│                 REST API (Axum)              │
│   /api/companies, /api/agents, /api/issues   │
├──────────┬──────────┬───────────────────────┤
│  Agent    │  Issue   │    Scheduler          │
│  Registry │  State   │  (cron + heartbeat)   │
│          │  Machine  │                       │
├──────────┴──────────┴───────────────────────┤
│              SQLite (rusqlite/sqlx)           │
└─────────────────────────────────────────────┘
```

## Tech Stack

- **Language:** Rust (dogfooding -- Geometry OS is Rust)
- **HTTP:** Axum
- **DB:** SQLite via SQLx (zero ops, single file, no Docker/Postgres)
- **Scheduler:** tokio-cron-scheduler for routines
- **Serialization:** serde + serde_json

## Schema (10 tables)

### companies
```
id            UUID PK
name          TEXT
description   TEXT
status        TEXT DEFAULT 'active'
issue_prefix  TEXT
issue_counter INTEGER DEFAULT 0
created_at    TIMESTAMP
updated_at    TIMESTAMP
```

### agents
```
id              UUID PK
company_id      UUID FK -> companies
name            TEXT
role            TEXT DEFAULT 'general'  (ceo, engineer, qa)
status          TEXT DEFAULT 'idle'     (idle, running, paused, error)
adapter_type    TEXT DEFAULT 'hermes_local'
adapter_config  JSON  (model, cwd, timeoutSec, hermesCommand, etc)
runtime_config  JSON  (heartbeat interval, cooldown)
reports_to      UUID FK -> agents (nullable)
permissions     JSON  ({canCreateAgents: bool})
last_heartbeat  TIMESTAMP
paused_at       TIMESTAMP
error_message   TEXT (nullable, set when status=error)
health_status   TEXT DEFAULT 'healthy'  (healthy, stale, dead, unknown)
health_check_at TIMESTAMP (last time we verified the agent is alive)
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

### issues
```
id               UUID PK
company_id       UUID FK -> companies
project_id       UUID FK -> projects (nullable)
parent_id        UUID FK -> issues (nullable)
title            TEXT
description      TEXT
status           TEXT DEFAULT 'backlog'
  States: backlog, todo, in_progress, in_review, done, cancelled
priority         TEXT DEFAULT 'medium'
  Values: critical, high, medium, low
assignee_agent_id UUID FK -> agents (nullable)
identifier       TEXT UNIQUE  (e.g. "GEO-42")
issue_number     INTEGER
origin_kind      TEXT DEFAULT 'manual'
origin_id        TEXT (nullable)
blocked_by       JSON  (array of issue identifiers, replaces regex on description)
started_at       TIMESTAMP
completed_at     TIMESTAMP
created_at       TIMESTAMP
updated_at       TIMESTAMP
```

### issue_comments
```
id              UUID PK
issue_id        UUID FK -> issues
body            TEXT
author_agent_id UUID FK -> agents (nullable)
author_user_id  TEXT (nullable)
created_at      TIMESTAMP
```

### projects
```
id           UUID PK
company_id   UUID FK -> companies
name         TEXT
description  TEXT
status       TEXT DEFAULT 'in_progress'
color        TEXT (nullable)
created_at   TIMESTAMP
updated_at   TIMESTAMP
```

### goals
```
id          UUID PK
company_id  UUID FK -> companies
title       TEXT
description TEXT
level       TEXT DEFAULT 'task'
status      TEXT DEFAULT 'planned'
parent_id   UUID FK -> goals (nullable)
created_at  TIMESTAMP
updated_at  TIMESTAMP
```

### labels
```
id          UUID PK
company_id  UUID FK -> companies
name        TEXT
color       TEXT
created_at  TIMESTAMP
```

### issue_labels (join table)
```
issue_id    UUID FK -> issues
label_id    UUID FK -> labels
PK (issue_id, label_id)
```

### routines
```
id                UUID PK
company_id        UUID FK -> companies
project_id        UUID FK -> projects (nullable)
title             TEXT
description       TEXT
assignee_agent_id UUID FK -> agents
cron_expression   TEXT
status            TEXT DEFAULT 'active'
concurrency       TEXT DEFAULT 'skip_if_active'
last_triggered_at TIMESTAMP
created_at        TIMESTAMP
updated_at        TIMESTAMP
```

### activity_log
```
id          UUID PK
company_id  UUID FK -> companies
actor_type  TEXT  (user, agent, system)
actor_id    TEXT
action      TEXT
entity_type TEXT
entity_id   TEXT
details     JSON (nullable)
created_at  TIMESTAMP
```

## Key Design Decisions

### 1. Issue State Machine (Enforced)

Paperclip's state transitions are just string fields. Ours are enforced:

```
backlog ──► todo ──► in_progress ──► in_review ──► done
  ▲                                            │
  └──────────── (QA rejects) ◄─────────────────┘
                                     │
                                     ▼
                               cancelled
```

Transitions are validated. Can't go from `backlog` to `done`. Can't go to
`done` without `in_review` (configurable per company, but default on).

### 2. No Throwaway Issues

Routines execute without creating "dispatch" issues. The routine run is
tracked in an in-memory log, not as a permanent issue. The issue counter
only increments for real work.

### 3. Structured Idempotency

Phase/subphase IDs are structured fields, not title matching:
- `phase_id: "P15A"` is the same everywhere
- Creating an issue with the same `phase_id` + `origin_kind` is idempotent
- No more duplicate GEO-242/GEO-245

### 4. Agent Health

Every heartbeat run updates `health_check_at`. A background task runs every
5 minutes and marks agents:
- `healthy`: checked in within 2x heartbeat interval
- `stale`: checked in within 10x heartbeat interval
- `dead`: no check-in for > 10x interval
- `error`: last heartbeat finished with error

Dead/stale agents trigger alerts (comment on their active issue, log event).

### 5. Dependency Tracking

`blocked_by` is a JSON array of issue identifiers, not regex in descriptions.
Built-in dependency resolver:
- `GET /api/issues/:id/blockers` returns unresolved blockers
- `GET /api/companies/:cid/issues?blocked=true` returns blocked issues
- Auto-promote: when an issue moves to `done`, check if any issues it blocks
  are now unblocked and move them from `backlog` to `todo`

### 6. Generic Dispatch

Instead of one routine per agent:
```
POST /api/companies/:cid/dispatch
{
  "role": "engineer",
  "strategy": "idle_first",  // find idle agent, assign highest-priority todo
  "issue_id": null           // null = auto-pick from todo queue
}
```

Also works as a routine trigger: "every 15 min, find idle engineers and
assign work."

## REST API (Paperclip-compatible shape)

The API mirrors Paperclip's endpoints so agents don't need code changes:

```
# Health
GET  /api/health

# Companies
GET  /api/companies
GET  /api/companies/:cid
GET  /api/companies/:cid/dashboard

# Agents
GET  /api/companies/:cid/agents
GET  /api/agents/:aid
POST /api/companies/:cid/agents
PATCH /api/agents/:aid
POST /api/agents/:aid/wakeup

# Issues
GET  /api/companies/:cid/issues
GET  /api/issues/:iid
POST /api/companies/:cid/issues
PATCH /api/issues/:iid
POST /api/issues/:iid/checkout
GET  /api/issues/:iid/comments
POST /api/issues/:iid/comments
GET  /api/issues/:iid/blockers

# Projects
GET  /api/companies/:cid/projects
GET  /api/projects/:pid

# Goals
GET  /api/companies/:cid/goals

# Labels
GET  /api/companies/:cid/labels
POST /api/companies/:cid/labels

# Routines (new, not in Paperclip)
GET  /api/companies/:cid/routines
POST /api/companies/:cid/routines
PATCH /api/routines/:rid

# Dispatch (new)
POST /api/companies/:cid/dispatch
```

Authentication: local_trusted mode (no auth, same as Paperclip).

## Migration Plan

### Phase 1: Build core (this document)
- Scaffold Rust project
- Implement schema + migrations
- Implement REST API (Paperclip-compatible shape)
- Implement heartbeat executor
- Implement routine scheduler

### Phase 2: Migrate
- Export Paperclip data via API
- Import into GeoForge SQLite
- Point agents at new service (port 3101 initially)
- Run both in parallel
- Switch over when confident

### Phase 3: Enhance
- Add health monitoring
- Add generic dispatch
- Add dependency tracking
- Add QA gates
- Add spec module (OpenSpec reader)

## Project Structure

```
geo-forge/
├── Cargo.toml
├── PLAN.md
├── migrations/
│   └── 001_init.sql
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── db/
│   │   ├── mod.rs
│   │   ├── models.rs
│   │   └── schema.rs
│   ├── routes/
│   │   ├── mod.rs
│   │   ├── health.rs
│   │   ├── companies.rs
│   │   ├── agents.rs
│   │   ├── issues.rs
│   │   ├── projects.rs
│   │   ├── goals.rs
│   │   ├── labels.rs
│   │   ├── routines.rs
│   │   └── dispatch.rs
│   ├── services/
│   │   ├── mod.rs
│   │   ├── agent_service.rs
│   │   ├── issue_service.rs
│   │   ├── company_service.rs
│   │   ├── heartbeat.rs
│   │   ├── scheduler.rs
│   │   └── health_monitor.rs
│   ├── state_machine.rs
│   └── error.rs
└── tests/
    ├── api_tests.rs
    └── state_machine_tests.rs
```

## Timeline

- Core CRUD + API: 2-3 days
- Heartbeat + scheduler: 1-2 days
- Migration script: 1 day
- Health monitoring + dispatch: 1-2 days

Total: ~1 week to parity with what we use from Paperclip.
