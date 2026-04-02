# Learnings: SEC-1 Manifest Foundation

## What worked

- Centralizing all workflow registrations in a single `WORKFLOW_MANIFEST` array eliminated the need to keep three separate lists in sync (skill-generation.ts, tool-detection.ts SKILL_NAMES, tool-detection.ts COMMAND_IDS).
- The `deployable` flag was essential to distinguish feedback (a skill-only template not deployed to tools) from the 11 deployable workflows. Without it, SKILL_NAMES would have 12 entries and break existing tests.
- Keeping the manifest helper functions (getManifestEntries, getSkillDirNames, getCommandIds) return only deployable entries by default means tool-detection.ts and skill-generation.ts need zero special-case logic.

## What didn't

- Initially forgot to re-export `WorkflowManifestEntry` type from manifest.ts, causing a TS2724 error. Had to add a re-export line.
- The `feedback` workflow was a surprise — it exists as a skill template in the workflow modules but was never registered in any of the three consumer lists. Discovered only when tests broke.

## What I'd do differently

- The manifest types file and manifest registry file could have been a single file — the split adds a layer of indirection that may not be worth it for this size of project. However, keeping types separate allows future consumers to import types without pulling in all the workflow module side-effects.

## pattern

- **[pattern]** (from SEC-1) [added] src/core/templates/manifest.ts

- **[pattern]** (from SEC-1) [modified] src/core/templates/skill-templates.ts

- **[pattern]** (from SEC-1) [added] src/core/templates/manifest-types.ts

- **[pattern]** (from SEC-1) [modified] src/core/shared/skill-generation.ts

- **[pattern]** (from SEC-1) [modified] src/core/shared/tool-detection.ts

## discovery

- **[discovery]** (from SEC-1) Agent strategy: created 3 files, modified 4 files, added tests, fix attempt

- **[pattern]** (from SEC-2) [modified] src/core/init.ts

- **[pattern]** (from SEC-2) [modified] src/core/update.ts

- **[pattern]** (from SEC-2) [modified] src/core/profile-sync-drift.ts

- **[pattern]** (from SEC-2) [modified] src/core/migration.ts

- **[pattern]** (from SEC-2) [added] src/core/templates/tool-profile-types.ts

- **[discovery]** (from SEC-2) Agent strategy: created 2 files, modified 8 files, added tests, fix attempt

# Learnings: SEC-3 Transform Pipeline

## What worked

- Defining the `Transform` interface with `scope`, `phase`, `priority`, `applies`, and `transform` gives a clean contract for ordering and filtering. The phase-then-priority sort is deterministic and easy to reason about.
- The built-in `openCodeHyphenTransform` was a clean 1:1 migration of the ad-hoc `tool.value === 'opencode' ? transformToHyphenCommands : undefined` pattern — the transform's `applies` function captures exactly that predicate.
- Creating `generateSkillContentWithPipeline` as a new function (rather than modifying `generateSkillContent`) preserves backward compatibility — the old `transformInstructions` callback still works for existing callers/tests.
- Re-exporting transform types from `skill-templates.ts` and `transform-pipeline.ts` keeps the public API surface consistent with how SEC-1 and SEC-2 were exported.

## What didn't

- The `init.ts` and `update.ts` files have corrupted redacted bytes (`***` patterns) on some lines (e.g., init.ts lines 379, 390, 392, 396) which makes targeted patching difficult. Had to carefully avoid those lines.
- `update.ts` had two separate ad-hoc transform sites (the main update loop at ~line 225 and a legacy-upgrade path at ~line 735) — easy to miss the second one.

## What I'd do differently

- Could have used a single pipeline-aware function instead of keeping both `generateSkillContent` and `generateSkillContentWithPipeline`. The dual API is temporary — future tasks should migrate remaining direct callers to the pipeline version and deprecate the `transformInstructions` parameter.

## pattern

- **[pattern]** (from SEC-3) [added] src/core/templates/transform-types.ts
- **[pattern]** (from SEC-3) [added] src/core/templates/transform-pipeline.ts
- **[pattern]** (from SEC-3) [modified] src/core/shared/skill-generation.ts
- **[pattern]** (from SEC-3) [modified] src/core/shared/index.ts
- **[pattern]** (from SEC-3) [modified] src/core/templates/skill-templates.ts
- **[pattern]** (from SEC-3) [modified] src/core/init.ts
- **[pattern]** (from SEC-3) [modified] src/core/update.ts

## discovery

- **[discovery]** (from SEC-3) Agent strategy: created 2 files, modified 5 files, no new tests (existing parity tests cover transform output)
- **[discovery]** (from SEC-3) Pre-existing test failures (5 tests in artifact-workflow.test.ts and basic.test.ts) are unrelated to the transform pipeline — they fail on the `experimental` command alias which has a separate `--tool` flag parsing issue.

- **[pattern]** (from SEC-3) [modified] src/core/init.ts

- **[pattern]** (from SEC-3) [modified] src/core/update.ts

- **[pattern]** (from SEC-3) [modified] src/core/templates/skill-templates.ts

- **[pattern]** (from SEC-3) [added] src/core/templates/transform-pipeline.ts

- **[pattern]** (from SEC-3) [added] src/core/templates/transform-types.ts

- **[discovery]** (from SEC-3) Agent strategy: created 2 files, modified 7 files, added tests, fix attempt

- **[discovery]** (from SEC-4) Agent strategy: no-action

- **[pattern]** (from SEC-4) [modified] src/core/init.ts

- **[pattern]** (from SEC-4) [modified] src/core/update.ts

- **[pattern]** (from SEC-4) [added] src/core/templates/artifact-sync-engine.ts

- **[discovery]** (from SEC-4) Agent strategy: created 1 file, modified 2 files, added tests, fix attempt

# Learnings: SEC-5 Validation and Tests

## What worked

- Splitting tests into 4 focused files by concern (manifest completeness, tool-profile consistency, transform pipeline, matrix parity) makes failures easy to locate.
- Testing the full workflow/tool matrix (5 representative tools x 11 workflows) caught the opencode transform differentiation and YAML frontmatter consistency.
- Using content hashes for stability tests is fast and deterministic — no filesystem IO needed.
- The `invalidateToolProfileCache()` function in beforeEach was essential for test isolation since the profile registry is memoized.

## What didn't

- Had a variable shadowing bug (`template` vs `t` in a filter callback) that only showed at runtime — TypeScript's lint didn't catch it because `template` was in scope from the outer function (but undefined in the arrow callback). Will be more careful with arrow function variable names.

## What I'd do differently

- Could have combined manifest-completeness and tool-profile-consistency into one file since they're both structural validation. The 4-file split is slightly over-granular for this project size but keeps individual test runs fast.

## discovery

- **[discovery]** (from SEC-5) Agent strategy: created 4 files, modified 0 source files, added 66 tests (all passing)
- **[discovery]** (from SEC-5) Pre-existing test failures (5 tests) remain unchanged — all in `experimental` command alias path unrelated to the template generation pipeline.
- **[discovery]** (from SEC-5) All 22 AI_TOOLS entries have consistent profiles. All 22 registered adapters have matching AI_TOOLS entries. The manifest-skill-generation parity is exact (11 deployable workflows = 11 skill templates = 11 command templates).
