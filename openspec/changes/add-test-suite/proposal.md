## Why

AIPM has ~10,150 lines of Python across 33 modules and zero Python tests. The only test file is a JS theme-manager test. Every change to the codebase is deployed without verification. The loop has been running with 143/255 outcomes being "no_change" -- bugs could hide anywhere and we'd never know.

## What Changes

- Add pytest configuration to pyproject.toml
- Create `tests/` directory structure mirroring `aipm/`
- Write unit tests for the most critical modules first (outcome parsing, spec queue, model router, prompt strategies)
- Add integration tests for the spec pipeline (discover -> queue -> prompt)
- Add CI workflow for automated test runs

## Success Criteria

- `pytest tests/` runs and passes with 50+ tests
- Tests cover: outcome parsing, spec queue CRUD, spec discovery, prompt strategy selection, model routing, state management, config loading
- No changes to production code to make tests pass (tests should validate existing behavior)
- `pyproject.toml` updated with pytest config and dev dependencies

## Impact

- **New files**: `tests/` directory with ~10-15 test files
- **Modified**: `pyproject.toml` (add pytest deps and config)
- **No changes to source code**: Tests verify existing behavior
