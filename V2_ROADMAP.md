# Geo-Forge v2 Roadmap

Inspired by Anthropic's Conway architecture. v1 (tagged `v1-stable`) is production and untouched.
All v2 work happens on the `v2` branch.

## Guiding Insight

Conway's architecture proves the future isn't smarter models -- it's better agent infrastructure.
Our v1 already has multi-agent orchestration. v2 closes the gaps:

1. **Push, not pull** -- events drive work, not polling
2. **Agents remember** -- outcomes become searchable context for future runs
3. **Humans can inject** -- mid-execution guidance without restarts
4. **Tools are modular** -- drop-in tool packs, not hardcoded capabilities

---

## V2 Phases

### V2-P1: Event System & Webhooks (Forge)
**Goal:** Replace polling with push-based dispatch.

- Add `webhooks` table to DB (event_type, target_url, secret, active)
- Add `POST /webhooks` CRUD endpoints
- Add `POST /hooks/:event_type` inbound endpoint (signed with HMAC)
- Emit internal events on: issue status change, agent status change, heartbeat timeout
- Webhook delivery worker: retry with exponential backoff, log deliveries
- Harness subscribes to events instead of (or in addition to) polling

**Tables:**
```sql
webhooks (id, company_id, event_type, target_url, secret, active, created_at)
webhook_deliveries (id, webhook_id, payload, status, attempts, last_attempt, created_at)
events (id, company_id, event_type, payload JSON, created_at)
```

**Estimate:** ~400 lines new Rust, 1 new route file, 1 new service

### V2-P2: Outcome Memory (Harness + RAG)
**Goal:** Every completed issue feeds a searchable knowledge base.

- After issue completion, harness writes structured outcome:
  - Files touched, approach taken, errors hit, what worked, what didn't
  - LLM-generated summary of the solution
- Outcomes stored in RAG DB (`~/zion/projects/rag/rag/rag.db`)
- Before starting a new issue, harness queries RAG for related past outcomes
- New tool: `search_memory(query)` -- searches past outcomes via embeddings
- New tool: `save_outcome(issue_id, summary, files, approach)` -- stores outcome

**Harness changes:**
- New module: `geo_harness/memory.py` -- RAG client
- New tools in loop: `search_memory`, `save_outcome`
- Config: `rag_db_path` in config.yaml

**Estimate:** ~300 lines Python, mostly in memory.py

### V2-P3: Human Injection Channel (Forge + Harness)
**Goal:** Humans can inject guidance into a running worker without restart.

- Forge endpoint: `POST /agents/:id/inject` -- queues a message for the agent
- New table: `agent_injections (id, agent_id, message, read, created_at)`
- Harness picks up injections on each loop iteration, injects into LLM context
- Injection appears as a system message: "[Human Guidance]: ..."
- After reading, injection marked as `read=true`

**Estimate:** ~150 lines Rust, ~50 lines Python

### V2-P4: Tool Packs (Harness)
**Goal:** Tools are drop-in packages, not hardcoded.

- Define tool pack manifest format:
  ```
  tools/
    rust-debug/
      manifest.yaml  (name, version, tools, dependencies)
      tools.py       (tool implementations with Pydantic schemas)
    test-writer/
      manifest.yaml
      tools.py
  ```
- Harness scans `--tools-dir` on startup, loads packs dynamically
- Each pack declares what issue types it handles
- Config: `tools_dir: ./tools` in config.yaml

**Estimate:** ~250 lines Python, refactor of existing tool loading

### V2-P5: Worker Internals -- Context Prefetch
**Goal:** Workers use idle time productively (Conway's "forked subagents" concept).

- While waiting for LLM response or build, worker prefetches context for next issue
- Background thread reads issue backlog and RAG-prepares summaries
- When current issue completes, next issue's context is already warm
- Inspired by Conway's forked subagents for background indexing

**Estimate:** ~200 lines Python

---

## What We're NOT Building

- Buddy/gamification -- workers are headless
- Undercover mode -- no stealth contributions
- Managed service -- self-hosted is the right call
- Conway-style UI -- we have the overseer dashboard

---

## Migration Path

v1 and v2 share the same DB schema. v2 migrations are additive only:
- New tables (webhooks, events, agent_injections) don't touch v1 tables
- New columns are nullable with sensible defaults
- v1 code continues to work on a v2 DB (forward compatible)

To roll back: switch branch to main, tag v1-stable is always there.

## Success Metric

v2 is done when:
- [x] A worker starts working within 1 second of an issue being created (webhooks) -- V2-P1 DONE
- [x] A worker references past outcomes when solving a new issue (memory) -- V2-P2 DONE
- [x] Jericho can inject guidance into a running worker (injection channel) -- V2-P3 DONE
- [x] Adding a new tool is "create a directory with manifest.yaml" (tool packs) -- V2-P4 DONE
