# Learnings: add-change-stacking-awareness


## discovery

- **[discovery]** (from SEC-1) Agent strategy: created 1 file, modified 1 file

- **[discovery]** (from SEC-1) Agent strategy: no-action

- **[discovery]** (from SEC-1) Agent strategy: no-action

## SEC-1 implementation (attempt 4 - successful)

- The ChangeMetadataSchema lives in `src/core/artifact-graph/types.ts`, not in `src/core/schemas/change.schema.ts`. The `change.schema.ts` has ChangeSchema for proposal parsing, while ChangeMetadataSchema is for `.openspec.yaml` files.
- Stack fields are all optional (z.array(z.string()).optional() / z.string().optional()), which guarantees backward compatibility -- existing changes without these fields parse fine.
- The vitest config was pointing to `tests/**/*.test.ts` (nonexistent dir) instead of `test/**/*.test.ts`. Fixed so tests actually run.
- Pre-existing test failures: 3 files, 6 tests -- all unrelated (update.test.ts, basic.test.ts, artifact-workflow.test.ts). These are EACCES permission and skill file generation issues.
- Simplest possible approach worked: add 5 optional fields to the Zod schema, write tests. No new files in src/, no runtime code changes needed since Zod handles parsing/validation and the existing readChangeMetadata/writeChangeMetadata already use the schema.


## pattern

- **[pattern]** (from SEC-1) [modified] vitest.config.ts

- **[pattern]** (from SEC-1) [modified] src/core/artifact-graph/types.ts

- **[pattern]** (from SEC-1) [added] src/core/output-management/session-miner.ts

- **[pattern]** (from SEC-1) [modified] openspec/changes/add-change-stacking-awareness/learnings.md

- **[pattern]** (from SEC-1) [modified] openspec/changes/add-change-stacking-awareness/tasks.md

- **[discovery]** (from SEC-1) Agent strategy: created 2 files, modified 4 files, added tests, fix attempt

## SEC-2 implementation

- Created `src/core/validation/stack-validator.ts` as a standalone module with pure functions. No class needed -- `validateChangeStack()` takes an array of ChangeEntry objects and returns a StackValidationResult with errors/warnings.
- The existing `src/core/validation/` directory already had types.ts (ValidationIssue, ValidationReport) and validator.ts. The stack-validator is a separate concern (cross-change validation vs single-change validation), so a separate module is cleaner than extending the Validator class.
- Cycle detection uses DFS with parent tracking to reconstruct the full cycle path. Only reports the first cycle found (deterministic, since we sort change IDs before traversal).
- Transitive blocking detection walks the dependency tree to find changes blocked by upstream missing deps, but avoids duplicating errors already reported by the direct missing-dep or cycle checks.
- TypeScript strict mode requires `Array.from(map.keys())` instead of `[...map.keys()]` for Map iteration (downlevelIteration flag issue). Vitest/Vite handles this fine at runtime, but the lint checker complains.
- Overlap and requires warnings use sorted iteration for deterministic output ordering, which is important for test assertions and CLI consistency.
- 23 tests covering all 5 sub-steps, including edge cases (empty changes, self-referential deps, diamond dependencies, combined scenarios).

- **[pattern]** (from SEC-2) [modified] src/core/prompt-builder.ts

- **[pattern]** (from SEC-2) [modified] src/core/scheduler.ts

- **[pattern]** (from SEC-2) [modified] src/core/output-management/outcome-correlator.ts

- **[pattern]** (from SEC-2) [modified] src/core/output-management/session-miner.ts

- **[pattern]** (from SEC-2) [added] src/core/validation/stack-validator.ts

- **[discovery]** (from SEC-2) Agent strategy: created 2 files, modified 6 files, added tests, fix attempt

## SEC-3 implementation

- Created `src/core/validation/topological-sort.ts` with two exports: `topologicalSort()` and `getUnblockedChanges()`. Both functions validate for cycles first (delegating to `validateChangeStack` from SEC-2), then compute depth-based ordering.
- Added `graph()` and `next()` methods to `ChangeCommand` in `src/commands/change.ts`. These load active change metadata via `readChangeMetadata` and delegate to the topological sort module. Both support `--json` for machine-readable output.
- Registered `openspec change graph` and `openspec change next` subcommands in `src/cli/index.ts`.
- `getUnblockedChanges` does transitive blocking: if change A has a missing dep, any change depending on A is also excluded. This required a recursive `isBlocked()` check with memoization.
- Deterministic tie-breaking: at equal depth, changes are sorted lexicographically by ID. Verified with tests that input order doesn't affect output order.
- 18 tests total covering: basic ordering (empty, single, linear chain, diamond), deterministic tie-breaking (same depth lex sort, complex graph, input order independence), cycle detection, unknown dep handling, unblocked filtering (with missing deps, transitive blocking), and edge cases.
- The `GraphResult` type includes both `nodes: GraphNode[]` and `cycleError: string | null` so consumers can detect cycles without parsing error output.

- **[pattern]** (from SEC-3) [modified] src/core/scheduler.ts

- **[pattern]** (from SEC-3) [added] src/core/validation/topological-sort.ts

- **[pattern]** (from SEC-3) [modified] src/cli/index.ts

- **[pattern]** (from SEC-3) [modified] src/commands/change.ts

- **[pattern]** (from SEC-3) [modified] openspec/changes/add-change-stacking-awareness/learnings.md

- **[discovery]** (from SEC-3) Agent strategy: created 2 files, modified 5 files, added tests, fix attempt

## SEC-4 implementation (Split Scaffolding)

- Created `src/core/validation/change-splitter.ts` as a standalone module with pure functions: `splitChange()`, `findChildren()`, `generateChildIds()`. Follows same pattern as `stack-validator.ts` and `topological-sort.ts`.
- Added `split()` method to `ChangeCommand` in `src/commands/change.ts`. Registered `openspec change split <change-id>` subcommand in `src/cli/index.ts` with `--slices`, `--names`, `--overwrite`/`--force`, `--json` options.
- The split operation: (1) validates source change exists, (2) checks for existing children (errors without --overwrite), (3) creates child directories with `.openspec.yaml` (parent + dependsOn metadata), `proposal.md` stub, `tasks.md` stub, (4) appends "Split Status" section to parent's proposal.md.
- `writeChangeMetadata()` from `change-metadata.ts` validates schema names against `listSchemas()`. In tests with temp directories, the package-level `schemas/spec-driven` directory is still found (it's resolved relative to the module, not CWD), so `spec-driven` schema works in test environments.
- Re-split protection: `findChildren()` scans all change directories for those with `parent` metadata pointing to the source change ID. Returns sorted results for deterministic error messages.
- Overwrite mode removes old children before re-scaffolding. The parent proposal's "Split Status" section is idempotent (won't duplicate on re-split due to the `includes('**Split into slices:**')` guard).
- 27 tests covering: generateChildIds (determinism, custom names, min 2 slices), findChildren (empty, single, multiple sorted, no metadata), splitChange (source not found, default 2 slices, correct metadata, proposal/tasks stubs, .openspec.yaml, parent conversion, custom slices, custom names, schema inheritance), re-split protection (error without overwrite, deterministic error message), overwrite mode (success after initial split, old children removed, --force alias), output structure validation (valid directories, readable metadata).
- Pre-existing test failures remain at 3 files / 6 tests (basic.test.ts, artifact-workflow.test.ts, update.test.ts) -- all EACCES/skill generation issues, unrelated to this change.

- **[pattern]** (from SEC-4) [added] src/core/validation/change-splitter.ts
- **[pattern]** (from SEC-4) [added] test/core/validation/change-splitter.test.ts
- **[pattern]** (from SEC-4) [modified] src/cli/index.ts
- **[pattern]** (from SEC-4) [modified] src/commands/change.ts
- **[pattern]** (from SEC-4) [modified] openspec/changes/add-change-stacking-awareness/tasks.md

- **[discovery]** (from SEC-4) Agent strategy: created 2 files, modified 4 files, added tests

- **[pattern]** (from SEC-4) [modified] aipm-test.yaml

- **[pattern]** (from SEC-4) [modified] src/core/scheduler.ts

- **[pattern]** (from SEC-4) [added] src/core/validation/change-splitter.ts

- **[pattern]** (from SEC-4) [modified] src/cli/index.ts

- **[pattern]** (from SEC-4) [modified] src/commands/change.ts

- **[discovery]** (from SEC-4) Agent strategy: created 2 files, modified 6 files, added tests

## SEC-5 implementation (Documentation)

- Documentation-only task. No source code changes needed. Modified 4 markdown files: `docs/concepts.md`, `docs/cli.md`, `docs/workflows.md`, `docs/migration-guide.md`.
- Read the actual implementation files (`types.ts`, `stack-validator.ts`, `topological-sort.ts`, `change-splitter.ts`, `change.ts`, `cli/index.ts`) before writing docs to ensure accuracy. This is critical — the proposal described features at a high level but the actual CLI flags, JSON output shapes, and error messages have specific details that must match.
- Key gotcha: `provides`/`requires` do NOT create implicit dependency edges. This was explicitly stated in the proposal and implemented that way, but it's an important semantic to document clearly so users don't assume `requires` auto-wires dependencies.
- The Summary table in cli.md uses pipe-table formatting. Adding a new row between existing rows required keeping consistent pipe alignment to avoid breaking the markdown table.
- The `docs/workflows.md` already had a "Parallel Changes" section but no guidance on splitting. The new "Splitting Large Changes" section complements it by explaining the decomposition workflow.
- Pre-existing test failures (6 tests in artifact-workflow.test.ts) remain unchanged — they're skill file generation issues unrelated to docs.

- **[pattern]** (from SEC-5) [modified] docs/workflows.md

- **[pattern]** (from SEC-5) [modified] docs/cli.md

- **[pattern]** (from SEC-5) [modified] docs/concepts.md

- **[pattern]** (from SEC-5) [modified] docs/migration-guide.md

- **[pattern]** (from SEC-5) [modified] src/core/prompt-builder.ts

- **[discovery]** (from SEC-5) Agent strategy: created 4 files, modified 7 files, added tests, fix attempt
