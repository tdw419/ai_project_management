# GeoForge AI Agent Guide

Everything an AI agent needs to use GeoForge. One page, zero prior context required.

## What GeoForge Is

GeoForge is an issue tracker and agent orchestrator. It manages companies, agents, issues, and the lifecycle of autonomous work. Think of it as a project management API where both humans and AI agents are first-class users.

## Connection

```
Base URL: http://localhost:3101
Content-Type: application/json
```

All endpoints return JSON. CORS is enabled for all origins in dev.

## Authentication

None. GeoForge runs locally and trusts all callers. Identify yourself by passing your agent ID in requests.

## Core Concepts

### Company
The top-level container. Everything belongs to a company. A company has an `issue_prefix` (e.g. "GEO") that prefixes all issue identifiers (GEO-1, GEO-2, etc.).

### Agent
An AI or human worker registered with a company. Agents have roles ("engineer", "qa", "ceo", "general"), statuses ("idle", "running", "paused", "error", "deleted"), and capabilities.

### Issue
A unit of work. Issues have statuses, priorities, assignments, and can block each other.

### Issue Lifecycle
```
backlog -> todo -> in_progress -> in_review -> done
   |          |         |             |
   v          v         v             v
cancelled  cancelled  cancelled    cancelled
```

When qa_gate is enabled on the company, `in_progress -> done` is rejected. Must go through `in_review` first.

Issues with `blocked_by` dependencies start in `backlog`. When all blockers resolve (done/cancelled), they auto-promote to `todo`.

### Priority Order
`critical` > `high` > `medium` > `low`

## Geometry OS Company

The real Geometry OS company:
```
company_id: 41e9e9c7-38b4-45a8-b2cc-c34206d7d86d
issue_prefix: GEO
```

Do NOT use the test company (43aec661-3439-4525-9914-ecd2f78c27c8, prefix GEOA).

## Quick Start: Agent Lifecycle

### 1. Register yourself

```bash
POST /api/companies/{company_id}/agents/register
{
  "name": "my-agent",
  "role": "engineer",
  "adapter_type": "hermes_local",
  "capabilities": ["rust", "testing", "git"]
}
```

Response includes your `agent.id` and any issues auto-assigned to you. Save your agent ID -- you'll use it everywhere.

If you're re-registering after a restart, pass your previous `agent_id` to reclaim your identity:

```json
{
  "name": "my-agent",
  "role": "engineer",
  "agent_id": "447d735e-7374-4748-939f-126c1071d749"
}
```

### 2. Send heartbeats

```bash
POST /api/agents/{agent_id}/heartbeat
{
  "status": "running",
  "current_issue_id": "optional-issue-id",
  "progress_notes": "Working on the parser refactor"
}
```

Send every 30-60 seconds while active. If you stop heartbeating, the health checker will eventually mark you stale/dead.

### 3. Pick up work

Option A -- Dispatch (forge assigns you the next priority issue):
```bash
POST /api/companies/{company_id}/dispatch
{
  "role": "engineer"
}
```

Option B -- Checkout a specific issue:
```bash
POST /api/issues/{issue_id}/checkout
{
  "agent_id": "your-agent-id",
  "expected_statuses": ["todo"]
}
```

Both set the issue to `in_progress` and assign it to you.

### 4. Report results

Update the issue when done:
```bash
PATCH /api/issues/{issue_id}
{
  "status": "in_review",
  "description": "Added base_name() method to gasm.rs. All tests pass."
}
```

Or if qa_gate is off:
```json
{"status": "done"}
```

### 5. Add comments for context

```bash
POST /api/issues/{issue_id}/comments
{
  "body": "Implementation notes: changed the struct to include a base_name field..."
}
```

## Full API Reference

### Health & Meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Server health check |
| GET | `/api/metrics` | Request metrics |
| GET | `/api/stats` | Global statistics |

### Companies

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies` | List all companies |
| POST | `/api/companies` | Create company |
| GET | `/api/companies/{cid}` | Get company details |
| GET | `/api/companies/{cid}/dashboard` | Dashboard summary (agent counts, issue counts by status) |

### Agents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/agents` | List agents in company |
| POST | `/api/companies/{cid}/agents` | Create agent manually |
| POST | `/api/companies/{cid}/agents/register` | Register/re-register (preferred) |
| GET | `/api/agents/{aid}` | Get agent details |
| PATCH | `/api/agents/{aid}` | Update agent |
| DELETE | `/api/agents/{aid}` | Soft-delete agent, unassign its issues |
| POST | `/api/agents/{aid}/wakeup` | Wake agent, auto-dispatch next issue |
| POST | `/api/agents/{aid}/invoke` | Invoke agent on specific issue |
| POST | `/api/agents/{aid}/heartbeat` | Heartbeat with optional status payload |

### Issues

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/issues` | List issues (filterable) |
| POST | `/api/companies/{cid}/issues` | Create issue |
| GET | `/api/issues/{iid}` | Get issue (by UUID or identifier like "GEO-7") |
| PATCH | `/api/issues/{iid}` | Update issue (status, assignee, etc.) |
| DELETE | `/api/issues/{iid}` | Soft-delete (set to cancelled) |
| POST | `/api/issues/{iid}/checkout` | Claim issue for an agent |
| GET | `/api/issues/{iid}/blockers` | Check unresolved blockers |
| GET | `/api/issues/{iid}/comments` | List comments |
| POST | `/api/issues/{iid}/comments` | Add comment |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/projects` | List projects |
| POST | `/api/companies/{cid}/projects` | Create project |
| GET | `/api/projects/{pid}` | Get project |
| PATCH | `/api/projects/{pid}` | Update project |

### Goals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/goals` | List goals |
| POST | `/api/companies/{cid}/goals` | Create goal |
| PATCH | `/api/goals/{gid}` | Update goal |

### Labels

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/labels` | List labels |
| POST | `/api/companies/{cid}/labels` | Create label |

### Routines (Recurring Tasks)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/routines` | List routines |
| POST | `/api/companies/{cid}/routines` | Create routine |
| PATCH | `/api/routines/{rid}` | Update routine |
| DELETE | `/api/routines/{rid}` | Delete routine |
| POST | `/api/routines/{rid}/trigger` | Manually trigger |
| GET | `/api/routines/{rid}/runs` | List run history |

### Dispatch

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/companies/{cid}/dispatch` | Auto-assign best issue to idle agent |

### Activity Log

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/activity` | List all activity (filterable) |

### Specs (OpenSpec Documents)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/specs` | List spec documents |
| POST | `/api/companies/{cid}/specs` | Upload a spec |
| GET | `/api/specs/{sid}` | Get spec with parsed changes |
| DELETE | `/api/specs/{sid}` | Delete spec |
| POST | `/api/specs/{sid}/import` | Import spec changes as issues |
| GET | `/api/specs/{sid}/issues` | List issues created from spec |

### Alert Rules

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/alert-rules` | List alert rules |
| POST | `/api/companies/{cid}/alert-rules` | Create alert rule |
| DELETE | `/api/alert-rules/{rid}` | Delete alert rule |
| POST | `/api/companies/{cid}/alerts/evaluate` | Evaluate all rules |

### Outcome Verification

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/issues/{iid}/verify` | Submit outcome after work (tests, files, build) |
| GET | `/api/issues/{iid}/outcomes` | All outcomes for an issue |

### Strategy Templates

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/strategies` | List all strategy templates |
| GET | `/api/strategies/{name}/prompt` | Get prompt for a strategy |
| PATCH | `/api/strategies/{name}/prompt` | Update a strategy's prompt |

### Learnings (Self-Improvement)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/{cid}/learnings` | Aggregated learnings (success rates, trends, recommendations) |
| GET | `/api/companies/{cid}/learnings/modules` | Module difficulty tracking |
| POST | `/api/companies/{cid}/learnings/recompute` | Recompute from outcome history |

## Common Patterns

### Create an issue with file constraints

The description field is free-text. To constrain an agent to specific files, include a "FILES YOU MAY MODIFY" section:

```bash
POST /api/companies/{cid}/issues
{
  "title": "Add base_name() method to gasm",
  "description": "Add a method that returns the filename without extension.\n\nFILES YOU MAY MODIFY:\n- geometry_os/src/gasm.rs",
  "priority": "high",
  "project_id": "optional-project-uuid"
}
```

The geo-harness path guard reads this section and blocks writes to any file not listed.

### Create a chain of dependent issues

```bash
# First issue
POST /api/companies/{cid}/issues
{"title": "Design the API", "priority": "high"}
# Returns identifier: GEO-10

# Second issue blocked by the first
POST /api/companies/{cid}/issues
{"title": "Implement the API", "priority": "high", "blocked_by": ["GEO-10"]}
# Starts in "backlog", auto-promotes to "todo" when GEO-10 is done
```

### Check what's blocking an issue

```bash
GET /api/issues/{iid}/blockers
```

Returns `{"blockers": ["GEO-10"], "blocked": true}` if unresolved blockers exist.

### Dispatch work to an agent

```bash
# Auto-pick: find idle engineer, assign highest-priority todo
POST /api/companies/{cid}/dispatch
{"role": "engineer"}

# Specific agent + specific issue
POST /api/companies/{cid}/dispatch
{"agent_id": "uuid", "issue_id": "uuid"}
```

### Import a spec as issues

```bash
# Upload spec
POST /api/companies/{cid}/specs
{
  "title": "Phase 19: Texture Pipeline",
  "raw_content": "... OpenSpec document content ...",
  "project_id": "uuid"
}
# Returns spec with parsed_changes array

# Import all changes as issues
POST /api/specs/{spec_id}/import
{"indices": null}

# Or import specific changes only (0-based)
POST /api/specs/{spec_id}/import
{"indices": [0, 2]}
```

### Monitor activity

```bash
GET /api/companies/{cid}/activity
```

Returns all actions: issue.created, issue.checked_out, issue.updated, issue.auto_promoted, agent.register, agent.heartbeat, etc.

## Issue Identifiers

Issues have both a UUID `id` and a human-readable `identifier` (like "GEO-7"). Most endpoints accept either:

```bash
GET /api/issues/447d735e-7374-4748-939f-126c1071d749
GET /api/issues/GEO-7
```

Both work.

## Error Responses

All errors return JSON:

```json
{"error": "Description of what went wrong"}
```

HTTP status codes:
- `400` -- Validation error (bad input, invalid transition)
- `404` -- Resource not found
- `409` -- Conflict (wrong status for operation)
- `500` -- Internal error

## Registered Geometry OS Agents

| Name | Role | Agent ID |
|------|------|----------|
| Engineer | engineer | 447d735e-7374-4748-939f-126c1071d749 |
| RustEng | engineer | 059452a1-92fa-44fe-b591-b83f3d375c77 |
| CEO | ceo | 4d484dfa-ffe0-4b8c-870c-c9b23eadaf5a |
| QA | qa | 5ad57b5c-b21b-45fd-b719-87b5dbd22381 |

## Gotchas

1. **Two instances may be running.** Port 3101 is the harness-facing instance. Port 3100 may also be running. Always use 3101 for the real company (41e9e9c7).

2. **Issue identifiers are company-scoped.** "GEO-7" only resolves within the Geometry OS company. If you somehow have the wrong company_id, identifiers won't resolve.

3. **qa_gate is enabled.** You cannot go `in_progress -> done` directly. Must pass through `in_review` first.

4. **Auto-promotion fires on done/cancelled.** When an issue is resolved, all backlog issues that were only blocked by it automatically move to `todo`. This is logged as `issue.auto_promoted` in the activity log.

5. **Dispatch prefers unassigned issues.** It picks the highest-priority `todo` issue with no assignee, then falls back to issues assigned to the dispatching agent.

6. **Heartbeat or die.** If you stop sending heartbeats, the health checker marks you stale after 5 minutes and dead after 30 minutes. Dead agents get their issues unassigned.
