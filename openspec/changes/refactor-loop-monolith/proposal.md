## Why

`loop.py` is 1408 lines -- the single largest file, ~14% of the entire codebase. It handles project scanning, issue selection, prompt generation, agent execution, outcome parsing, state updates, follow-up creation, cross-project coordination, and more. This makes it hard to test, hard to reason about, and risky to modify.

The loop has grown organically as features were added. It should be decomposed into focused modules with clear responsibilities.

## What Changes

- Extract agent execution logic into `executor.py` (run agent, parse outcome, trust boundary)
- Extract cycle orchestration into `cycle.py` (select project, select issue, dispatch, follow-up)
- Keep `loop.py` as the top-level coordinator (scanning, scheduling, health checks)

## Success Criteria

- No module exceeds 400 lines
- Each module has a single clear responsibility
- All existing behavior preserved (no regression in loop execution)
- Executor and cycle modules are independently testable

## Impact

- **Modified**: `loop.py` (massive reduction)
- **New**: `executor.py`, `cycle.py`
- **Risk**: Medium -- core orchestration path. Must preserve exact behavior.
