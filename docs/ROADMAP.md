# AIPM Strategic Roadmap (2026-2027)

> Saved: 2026-03-27
> Source: Strategic planning session
> Auto-managed by AIPM Roadmap Processor

## Analysis Scores

| Metric | Score | Notes |
|--------|-------|-------|
| Key Insight | 0.95 | Architecture robust but needs automation for complex refactors |
| Strategic Direction | 1.0 | Focus on autonomy, empirical validation, multimodal |
| Ecosystem Alignment | 0.9 | Aligns with Geometry OS + OpenMind |

---

## Phase 1: Foundation & Reliability (Q2 2026)

**Focus:** Hardening the core loop and enhancing codebase awareness.

### 1. Dynamic Context Injection (Groundedness v2)

- [x] 🔥 Create RAG World Model module (`aipm/rag_context.py`)
- [ ] Integrate qwen3-coder-30b for dependency mapping
- [ ] Add semantic code analysis for diff summarization
- [ ] Wire RAG context into all prompt processing

### 2. Autonomous Recovery Protocols

- [ ] 🔥 Implement failover: LM Studio ↔ Pi Agent (GLM-5)
- [ ] Add self-healing for SQLite database locks
- [ ] Add recovery for corrupted state files
- [ ] Create health check endpoints

### 3. CLI/Dashboard Parity

- [ ] Full ASCII World Dashboard control
- [ ] Add "Pause for Human Oversight" breakpoints
- [ ] Enable loop start/stop from dashboard
- [ ] Real-time progress visualization

---

## Phase 2: Agentic Maturity & AutoSpec (Q3 2026)

**Focus:** Empirical validation and recursive problem solving.

### 1. Full AutoSpec Lifecycle

- [ ] 🔥 Automate H/T/M/B hypothesis testing cycle
- [ ] Auto-feed results.tsv → CTRM for learning
- [ ] Add hypothesis confidence scoring
- [ ] Implement budget tracking per hypothesis

### 2. Recursive Prompt Generation

- [ ] Enhance ResponseAnalyzer for PARTIAL results
- [ ] Auto-break large tasks into 5-10 sub-prompts
- [ ] Implement Long-Term Memory (LTM) for multi-day tasks
- [ ] Add task dependency tracking

### 3. Multi-Agent Coordination

- [ ] Integrate FABRIC protocol from OpenMind
- [ ] Enable distributed truth sharing
- [ ] Add peer registration and discovery
- [ ] Implement wisdom exchange protocols

---

## Phase 3: Autonomous Ecosystem & Geometry OS (Q4 2026+)

**Focus:** Reaching the "Perpetual Engineering Machine" state.

### 1. Visual Logic & Multimodal Awareness

- [ ] Integrate qwen/qwen3-vl-8b for vision tasks
- [ ] Enable UI regression detection via screenshots
- [ ] Implement "Spatial Debugging" in ASCII World
- [ ] Add Hilbert curve mappings for large codebases

### 2. Geometry OS Native Bootstrapping

- [ ] Configure AIPM to manage systems/infinite_map_rs
- [ ] Prioritize Rust compositor optimizations
- [ ] Implement "Self-Improving Drivers" for WGSL shaders
- [ ] Add 60fps consistency monitoring

### 3. The "Ouroboros" Finality

- [ ] 🔥 AIPM manages its own roadmap (this file!)
- [ ] Auto-enqueue feature requests from telemetry
- [ ] Self-refactor core engine based on usage patterns
- [ ] Achieve >95% autonomy ratio

---

## KPIs

| Metric | Target | Current |
|--------|--------|---------|
| Autonomy Ratio | >95% | ~80% |
| Validation Density | 100% | 0% |
| Loop Velocity | <60s | ~45s |

---

## Changelog

### 2026-03-27
- [x] Created roadmap document
- [x] Implemented RAG World Model (Phase 1.1)
- [x] Added roadmap processor module
