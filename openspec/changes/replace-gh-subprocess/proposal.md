## Why

All GitHub operations (issue creation/closing/reading, label management, PR creation) currently shell out to the `gh` CLI via `subprocess.run()`. This is fragile: requires `gh` installed and authenticated, hard to test, hard to handle errors, and slow (spawns a process per call). The `gh` CLI also has inconsistent JSON output across versions.

## What Changes

- Replace all `subprocess.run(["gh", ...])` calls with PyGitHub library calls
- Affected modules: `issue_queue.py`, `github_sync.py`, `auto_pr.py`, `loop.py`, `followup.py`, `rca.py`
- Add `PyGitHub` to pyproject.toml dependencies
- Add `GH_TOKEN` or `GITHUB_TOKEN` env var handling

## Success Criteria

- Zero `subprocess` calls to `gh` remain in the codebase
- All GitHub operations use PyGitHub
- Existing behavior preserved (issue creation, closing, labeling, PRs)
- Error handling is improved (no more parsing CLI output)

## Impact

- **Modified**: `issue_queue.py`, `github_sync.py`, `auto_pr.py`, `loop.py`, `followup.py`, `rca.py`
- **New dependency**: `PyGitHub` in pyproject.toml
- **Risk**: Medium -- touch many modules but each change is mechanical
