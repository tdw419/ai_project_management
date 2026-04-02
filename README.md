# AIPM v4 — Strategy-Driven Autonomous Coding Loop

AIPM (AI Project Management) is a high-performance orchestration layer for autonomous coding agents. It transforms static specifications into a dynamic, parallelized execution pipeline that thinks before it acts.

The Screen is the Hard Drive. Computation is Geometric.

## 🚀 Key Innovations

- **Strategy-Aware Cognition**: Automatically selects execution modes (`SCOUT`, `SURGEON`, `BUILDER`, `REFACTOR`, `FIXER`) based on task context and retry history.
- **Parallel Swarm**: Safely executes multiple concurrent agents across different changes using `fcntl` file-locking state management.
- **Outcome Overrides**: Never trust an agent's self-assessment. AIPM uses a dedicated `OutcomeDetector` to verify filesystem changes and test results before marking a task complete.
- **Learning Persistence**: Aggregates `learnings.md` from all active changes to inject project-wide context into agent prompts, preventing repeated mistakes.
- **Spec-First Lifecycle**: Integrated `openspec` support for drafting, tracking, and committing changes through a structured proposal/task system.

## 🛠 Installation

```bash
# Clone and install
git clone https://github.com/tdw419/ai_project_management
cd ai_project_management
pip install -e .
```

## 📖 Usage

### 1. Bootstrap a Project
Initialize the `openspec` structure in any repository:
```bash
aipm init
```

### 2. Draft a New Change
Scan your codebase and automatically generate a proposal and task list via LLM:
```bash
aipm draft "Add WebGPU support to the visual shell"
```

### 3. Run the Autonomous Loop
Start the parallel processing swarm:
```bash
# Run 3 concurrent agents in an autonomous loop
aipm run --loop --parallel 3 --agent hermes
```

### 4. Monitor & Inspect
List all active changes and their statuses:
```bash
aipm list
aipm next
```

## 🏗 Architecture

| Module | Responsibility |
|--------|----------------|
| `ParallelLoop` | Orchestrates concurrent task claiming and worker management. |
| `Executor` | Manages the implementation lifecycle (Plan → Act → Validate). |
| `StrategyEngine` | Determines the optimal cognitive mode for the current task. |
| `OutcomeDetector` | Empirically verifies work via git diffs and pytest results. |
| `StateStore` | Atomic, thread-safe persistence for task statuses. |

## 🧪 Testing

AIPM v4 is built with reliability in mind, featuring over 490+ passing tests covering stress conditions and edge cases.

```bash
python3 -m pytest tests/
```

---
"The era of symbolic computation is over. The era of geometric intelligence has begun."
