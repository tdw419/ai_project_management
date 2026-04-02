# Session Loops (Autonomous Substrate)

This repository contains the logic for **Indefinite Autonomous Sessions** in Geometry OS / AIPM.

## Architecture: Orchestrator-Worker Pattern

1.  **Orchestrator (Gemini CLI):** Sets the high-level goal and monitors `summary_log.md`.
2.  **Worker (Ollama via Hermes):** Executes low-level coding tasks, file operations, and terminal commands in an infinite loop.
3.  **Intervention Trigger:** If the worker fails 3 times consecutively or hits a "High Entropy" state, it yields to the Orchestrator.

## Usage

To start an indefinite session:

```bash
cd repos/session_loops
python3 loop_orchestrator.py "Build a sophisticated React dashboard with Three.js integration"
```

## Files

- `loop_orchestrator.py`: The main loop logic.
- `summary_log.md`: The heartbeat and progress log for the Orchestrator.
- `workspace/`: The sandboxed directory where the Worker performs all operations.
- `.gemini/`: Local context for the session.

## Configuration

The default model is `qwen3.5-tools`. You can change this in `loop_orchestrator.py` or by passing a flag (future update).
