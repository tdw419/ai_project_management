# Architecture: AIPM v2

## Overview

AIPM (Autonomous Project Management v2) is a Python orchestrator that manages multiple software projects autonomously. It reads work from spec files (openspec/) or GitHub Issues, generates context-grounded prompts, dispatches AI coding agents (Hermes), parses outcomes, and feeds learnings back into the system.

**Tech stack:** Python 3.10+, SQLite, subprocess calls to `gh`, `git`, `hermes`
**Size:** ~10,150 lines across 33 modules, 1 runtime dependency (pyyaml)
**Tests:** Zero Python tests (only a JS theme-manager test exists)
**CLI:** 15 subcommands via main.py

## Core Loop

```
Scan projects (repos/)
  -> Select project (round-robin + health)
    -> Read work queue (openspec/ first, then GH Issues)
      -> Generate spec-grounded prompt + select strategy
        -> Route to model (local vs cloud)
          -> Execute via Hermes agent
            -> Parse outcome (success/failure/no_change/etc)
              -> Update state, log prompt, write learnings
                -> Create follow-ups, PRs, cross-project issues
```

## Module Organization

### 1. Core Loop & Orchestration

| Module | Lines | Purpose |
|--------|-------|---------|
| `main.py` | 403 | CLI entry point. 15 commands: status, run, run-once, inject, pause, resume, boost, etc. |
| `loop.py` | 1408 | **Heart of the system.** `MultiProjectLoop` orchestrates the full 14-step cycle per project. |
| `config.py` | 109 | `ProjectConfig` dataclass, constants (DB paths, model defaults, provider config) |

### 2. Project Discovery

| Module | Lines | Purpose |
|--------|-------|---------|
| `scanner.py` | 99 | Scans repos/ for projects. Detects language from markers. |
| `repo_scaffold.py` | 191 | Creates new project scaffolds with git init + optional GitHub repo. |

### 3. State Management

| Module | Lines | Purpose |
|--------|-------|---------|
| `state.py` | 100 | `ProjectState` + `StateManager` -- SQLite-backed state per project (health, tests, failures). |

### 4. Work Queue

| Module | Lines | Purpose |
|--------|-------|---------|
| `issue_queue.py` | 405 | `GitHubIssueQueue` -- reads GH Issues as work items. Priority tiers, cooldown, dedup. |
| `github_sync.py` | 251 | Bidirectional sync with GitHub (labels, milestones, issue CRUD). |
| `priority.py` | 258 | Priority injection. Control file for pause/resume. Critical issue bypass. |

### 5. Spec System (OpenSpec Integration)

| Module | Lines | Purpose |
|--------|-------|---------|
| `spec/__init__.py` | 411 | Data models: Change, Task, Proposal, Requirements, Design, Learnings. Markdown serialization. |
| `spec_discoverer.py` | 361 | Scans openspec/changes/ directories, parses proposal/requirements/design/tasks into objects. |
| `spec_queue.py` | 505 | `SpecQueue` -- spec-driven work queue. Reads tasks from openspec/. Dependency resolution, status tracking. |
| `openspec_adapter.py` | 219 | Extracts complexity signals from specs for model routing. |

### 6. Prompt Generation

| Module | Lines | Purpose |
|--------|-------|---------|
| `driver.py` | 332 | `GroundedDriver` -- generates spec-grounded prompts. Falls back to feature lists. |
| `prompt_strategies.py` | 196 | Adaptive strategy selection: FRESH, RETRY, FIX_REGRESSION, DIFFERENT_APPROACH, SIMPLIFY, ABANDON. |

### 7. Model Routing

| Module | Lines | Purpose |
|--------|-------|---------|
| `model_router.py` | 574 | `select_model()` -- complexity scoring + outcome history. Routes local (Ollama) vs cloud (ZAI). |

### 8. Execution & Outcome

| Module | Lines | Purpose |
|--------|-------|---------|
| `outcome.py` | 325 | Parses agent output: SUCCESS, FAILURE, PARTIAL, NO_CHANGE, TRUST_VIOLATION, TIMEOUT, ERROR. |
| `trust.py` | 217 | File protection. SHA256 snapshots, auto-revert violations via git checkout. |
| `monte_carlo.py` | 290 | Parallel strategy execution via git worktrees. Picks best result. |
| `prompt_log.py` | 376 | SQLite-backed prompt/outcome log. Feeds strategy selection and model routing. |

### 9. Post-Execution

| Module | Lines | Purpose |
|--------|-------|---------|
| `followup.py` | 147 | Creates follow-up GH issues from unchecked tasks, missing coverage. |
| `rca.py` | 233 | Root Cause Analysis for abandoned issues. Pattern matching. |
| `cross_project.py` | 256 | Cross-project issue creation via depends_on/consumed_by relationships. |
| `learnings.py` | 196 | Writes learnings.md after outcomes. Collects for prompt enrichment. |
| `auto_pr.py` | 119 | Auto-creates PRs via `gh pr create` after success. |
| `session_historian.py` | 529 | Mines Hermes session transcripts for context injection. |

### 10. Monitoring

| Module | Lines | Purpose |
|--------|-------|---------|
| `watchdog.py` | 608 | Self-monitoring: anomaly detection, circuit-break, throttling. |
| `metrics.py` | 86 | SQLite time-series metrics for trend analysis. |
| `command_watcher.py` | 105 | File-based IPC for ascii_world web UI commands. |
| `ascii_bridge.py` | 140 | Box-drawn ASCII status formatter. |
| `webhook.py` | 183 | GitHub webhook listener (HTTP). HMAC verification. |

### 11. Roadmap & Templates

| Module | Lines | Purpose |
|--------|-------|---------|
| `roadmap_sync.py` | 210 | Scans ROADMAP.md, creates GH issues for unchecked items. |
| `install_templates.py` | 38 | Installs GH issue templates and AGENTS.md. |

## Known Issues

1. **Zero test coverage**: No Python tests exist. Only a JS theme-manager test.
2. **loop.py is a 1408-line monolith**: Orchestrates everything, imports from ~20 modules.
3. **Raw subprocess for `gh`**: All GitHub operations shell out to `gh` CLI. Fragile, hard to test.
4. **4 SQLite databases**: truths.db, queue.db, projects.db, aipm.db. No ORM, raw SQL. Schema drift risk.
5. **No dependency management**: Only pyyaml declared. Relies on system-installed `gh`, `git`, `hermes`.
6. **Deprecated v1 code**: `core/engine.py`, `core/queue.py`, `queue.py` still exist but unused.

## CLI Commands

| Command | Purpose |
|---------|---------|
| `status` | Show all projects, health, active issues |
| `run` | Continuous loop with interval |
| `run-once` | Single cycle |
| `inject` | Inject a critical task |
| `pause/resume` | Pause/resume specific projects |
| `boost` | Prioritize a project |
| `create-issue` | Create a GH issue |
| `labels` | Sync GH labels |
| `reset-health` | Reset project health to green |
| `new-project` | Scaffold a new project |
| `sync-roadmap` | Create issues from ROADMAP.md |
| `watchdog` | Start self-monitoring |
| `webhook` | Start webhook listener |
| `list-injected` | List injected tasks |
