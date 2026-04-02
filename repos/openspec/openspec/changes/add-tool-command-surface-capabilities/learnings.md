# Learnings: add-tool-command-surface-capabilities


## pattern

- **[pattern]** (from SEC-0) [modified] src/core/config.ts

- **[pattern]** (from SEC-0) [modified] src/core/shared/index.ts

- **[pattern]** (from SEC-0) [added] src/core/shared/command-surface.ts

- **[pattern]** (from SEC-0) [modified] openspec/changes/add-tool-command-surface-capabilities/tasks.md

- **[pattern]** (from SEC-0) [added] test/core/shared/command-surface.test.ts

## discovery

- **[discovery]** (from SEC-0) Agent strategy: created 2 files, modified 3 files, added tests

## SEC-3 learnings

- **[pattern]** (from SEC-3) [modified] src/core/update.ts - replaced global shouldGenerateSkills/shouldGenerateCommands booleans with per-tool capability resolution via surfaceMap
- **[pattern]** (from SEC-3) [modified] src/core/profile-sync-drift.ts - added toolEffectiveActions() helper, made hasToolProfileOrDeliveryDrift and hasProjectConfigDrift capability-aware
- **[pattern]** (from SEC-3) [modified] test/core/update.test.ts - updated old test expecting skill removal to expect skill retention for skills-invocable tools
- **[pattern]** (from SEC-3) [added] 5 new tests in test/core/update.test.ts under 'capability-aware update (SEC-3)' describe block
- **[discovery]** (from SEC-3) Tool detection requires at least one SKILL.md file to consider a tool "configured" - empty skillsDir is not enough. Tests must pre-create skill files.
- **[discovery]** (from SEC-3) The init.ts pattern from SEC-2 was directly reusable for update.ts - same toolShouldGenerateSkills/toolShouldGenerateCommands methods, same surfaceMap resolution.
- **[discovery]** (from SEC-3) Command file paths use short IDs (e.g. "explore.md") not prefixed names ("openspec-explore.md"). Check adapter.getFilePath() output.

- **[pattern]** (from SEC-3) [modified] src/core/update.ts

- **[pattern]** (from SEC-3) [modified] src/core/profile-sync-drift.ts

- **[pattern]** (from SEC-3) [modified] openspec/changes/add-tool-command-surface-capabilities/learnings.md

- **[pattern]** (from SEC-3) [modified] openspec/changes/add-tool-command-surface-capabilities/tasks.md

- **[pattern]** (from SEC-3) [modified] test/core/update.test.ts

- **[discovery]** (from SEC-3) Agent strategy: modified 5 files, refactored, fix attempt

## SEC-4 learnings

- **[pattern]** (from SEC-4) [modified] src/core/init.ts - added compatibility note for delivery=commands + skills-invocable, improved error message for incompatible tools
- **[pattern]** (from SEC-4) [modified] src/core/update.ts - aligned error message with init for incompatible tools
- **[pattern]** (from SEC-4) [added] test/core/sec4-ux-error-messaging.test.ts - 9 tests covering compatibility note, error wording, init/update alignment
- **[discovery]** (from SEC-4) CLI integration tests (runCLI) require rebuild (`pnpm run build`) before changes appear in subprocess output. The runCLI helper spawns dist/cli/index.js, not the source TypeScript.
- **[discovery]** (from SEC-4) The compatibility note appears during generation (before tool loop), while the summary "Skills used as command surface" appears after. Both are needed: proactive explanation + post-hoc summary.
- **[discovery]** (from SEC-4) Agent strategy: modified 2 source files, created 1 test file

- **[pattern]** (from SEC-4) [modified] src/core/init.ts

- **[pattern]** (from SEC-4) [modified] src/core/update.ts

- **[pattern]** (from SEC-4) [modified] openspec/changes/add-tool-command-surface-capabilities/learnings.md

- **[pattern]** (from SEC-4) [modified] openspec/changes/add-tool-command-surface-capabilities/tasks.md

- **[pattern]** (from SEC-4) [added] test/core/sec4-ux-error-messaging.test.ts

- **[discovery]** (from SEC-4) Agent strategy: created 1 file, modified 4 files, added tests

## SEC-5 learnings

- **[pattern]** (from SEC-5) [modified] docs/supported-tools.md - added "Command Surface Capabilities" section with resolution priority table, delivery mode interaction matrix, and Trae specifics
- **[pattern]** (from SEC-5) [modified] docs/cli.md - added "Delivery modes and tool capabilities" subsection under init docs, added "Troubleshooting" section with two entries (no-command-surface error, skills unexpectedly removed)
- **[discovery]** (from SEC-5) Documentation-only task. No source code changes needed. The command-surface model was already well-implemented; docs needed to catch up to reflect the capability-aware behavior from SEC-0 through SEC-4.
- **[discovery]** (from SEC-5) Agent strategy: modified 2 docs files, updated tasks.md. No test changes needed (docs don't affect tests).

- **[pattern]** (from SEC-5) [modified] docs/cli.md

- **[pattern]** (from SEC-5) [modified] docs/supported-tools.md

- **[pattern]** (from SEC-5) [modified] openspec/changes/add-tool-command-surface-capabilities/learnings.md

- **[pattern]** (from SEC-5) [modified] openspec/changes/add-tool-command-surface-capabilities/tasks.md

- **[discovery]** (from SEC-5) Agent strategy: modified 4 files, fix attempt

## SEC-6 learnings

- **[discovery]** (from SEC-6) Verification-only task. All 75 test files (1522 tests) pass with zero regressions.
- **[discovery]** (from SEC-6) Smoke checks confirmed correct behavior: `delivery=commands` + trae retains skills as command surface, `delivery=commands` + claude generates adapter commands (no skills), mixed tools produce correct per-tool artifact types.
- **[discovery]** (from SEC-6) CLI has no `--delivery` flag; delivery mode is set via `openspec config set delivery <mode>`. Non-interactive mode is triggered by `CI=1` env var, not `--no-interactive`.
- **[discovery]** (from SEC-6) The compatibility note ("Skills retained as command surface for: Trae") and summary line ("Skills used as command surface for: Trae") both appear correctly in smoke test output.

- **[pattern]** (from SEC-6) [modified] openspec/changes/add-tool-command-surface-capabilities/learnings.md

- **[pattern]** (from SEC-6) [modified] openspec/changes/add-tool-command-surface-capabilities/tasks.md

- **[discovery]** (from SEC-6) Agent strategy: modified 2 files

- **[discovery]** (from SEC-6) Tests improved by 1 (0 -> 1)
