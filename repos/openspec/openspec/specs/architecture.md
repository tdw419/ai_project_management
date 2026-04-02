# Architecture: OpenSpec

## Overview

OpenSpec (`@fission-ai/openspec`) is a TypeScript CLI tool for spec-driven development. It provides a structured workflow for proposing, designing, implementing, and verifying software changes through markdown-based specification documents. It supports 21+ AI coding tools (Claude, Cursor, Codex, Gemini, etc.) via pluggable adapters.

**Tech stack:** TypeScript, Node.js (>=20.19.0), ESM modules, Commander.js, Zod, Vitest
**Package:** ~18,700 lines across 101 source files, 1,341 tests (all passing)

## Layers

### 1. CLI Entry Point (`cli/`)

- **`cli/index.ts`** (510 lines) -- Commander.js program setup. Registers all subcommands: config, spec, schema, change, validate, show, completion, feedback, workflow, init, update, list, archive, view. Hooks telemetry and color flags.

### 2. Commands (`commands/`)

High-level CLI command implementations:

| File | Lines | Purpose |
|------|-------|---------|
| `schema.ts` | 1005 | Schema management (fork, init, validate, which) |
| `config.ts` | 645 | Profile/config management, workflow selection |
| `change.ts` | 292 | Change management commands |
| `validate.ts` | 326 | Validation of specs/changes |
| `completion.ts` | 306 | Shell completion (bash/zsh/fish/powershell) |
| `feedback.ts` | 208 | Feedback submission |
| `spec.ts` | 251 | Spec operations |
| `show.ts` | 138 | Display change/spec content |

### 3. Workflow Commands (`commands/workflow/`)

| File | Lines | Purpose |
|------|-------|---------|
| `instructions.ts` | 481 | Generate/apply instructions for AI tools |
| `new-change.ts` | 61 | Create new change |
| `status.ts` | 112 | Show project status |
| `templates.ts` | 98 | List available templates |
| `schemas.ts` | 46 | List available schemas |
| `shared.ts` | 164 | Shared types and utilities |

### 4. Core Engine (`core/`)

The business logic layer:

- **`init.ts`** (779 lines) -- Project initialization, tool detection, skill/command generation
- **`update.ts`** (702 lines) -- Update installed workflows and skills
- **`legacy-cleanup.ts`** (650 lines) -- Detect and clean up pre-OpenSpec project artifacts
- **`specs-apply.ts`** (483 lines) -- Apply spec updates to change directories
- **`archive.ts`** (339 lines) -- Archive completed changes
- **`view.ts`** (218 lines) -- View change/spec content
- **`list.ts`** (193 lines) -- List changes with status
- **`project-config.ts`** (264 lines) -- Project-level config validation
- **`profile-sync-drift.ts`** (240 lines) -- Detect profile/tool configuration drift
- **`config-schema.ts`** (243 lines) -- Global config schema with Zod
- **`global-config.ts`** (155 lines) -- Global config file management
- **`migration.ts`** (131 lines) -- Workflow migration logic
- **`config.ts`** (46 lines) -- Core constants (OPENSPEC_DIR_NAME, AI_TOOLS)
- **`profiles.ts`** (50 lines) -- Workflow profile definitions

### 5. Artifact Graph (`core/artifact-graph/`)

- **`graph.ts`** -- `ArtifactGraph` class for dependency tracking between specs, changes, and generated artifacts
- **`resolver.ts`** -- Schema resolution from package, user, and project directories
- **`instruction-loader.ts`** -- Template loading and instruction generation for changes
- **`schema.ts`** -- Schema loading and validation
- **`state.ts`** -- Detect completed artifacts
- **`types.ts`** -- Zod schemas for artifacts, changes, and metadata

### 6. Command Generation (`core/command-generation/`)

Generates tool-specific command/skill files:

- **`generator.ts`** -- Core generation logic
- **`registry.ts`** -- `CommandAdapterRegistry` for managing adapters
- **`adapters/`** -- 21 tool adapters (Claude, Cursor, Codex, Gemini, Windsurf, Cline, etc.)

### 7. Shell Completions (`core/completions/`)

Full shell completion support for bash, zsh, fish, and PowerShell:
- **Generators** -- Produce completion scripts per shell
- **Installers** -- Install completions into shell config files
- **Templates** -- Shell-specific helper function templates
- **`command-registry.ts`** -- 463 lines defining all commands and flags

### 8. Parsers (`core/parsers/`)

- **`markdown-parser.ts`** -- Generic markdown section parser
- **`change-parser.ts`** -- Change document parser extending MarkdownParser
- **`requirement-blocks.ts`** -- Requirement extraction with delta spec parsing

### 9. Validation (`core/validation/`)

- **`validator.ts`** (449 lines) -- Spec/change validation with configurable rules
- **`constants.ts`** -- Validation thresholds and messages

### 10. Templates (`core/templates/workflows/`)

12 workflow templates generating skill and command content:
- apply-change, archive-change, bulk-archive, continue-change
- explore, feedback, ff-change, new-change
- onboard, propose, sync-specs, verify-change

### 11. Supporting Modules

- **`telemetry/`** -- PostHog-based anonymous usage tracking with opt-out
- **`ui/`** -- ASCII welcome screen and animation patterns
- **`prompts/`** -- Searchable multi-select prompt for interactive CLI
- **`utils/`** -- File system, change metadata, shell detection, task progress, item discovery

## Change Status

### Completed (all tasks done)
- `fix-opencode-commands-directory` (5/5 tasks)
- `graceful-status-no-changes` (8/8 tasks)
- `simplify-skill-installation` (90/90 tasks)

### In Progress (has unchecked tasks)
- `add-change-stacking-awareness` (0/22 tasks)
- `add-global-install-scope` (0/38 tasks)
- `add-tool-command-surface-capabilities` (0/33 tasks)
- `unify-template-generation-pipeline` (0/24 tasks)

### Proposal Only (no tasks.md yet)
- `add-artifact-regeneration-support`
- `add-qa-smoke-harness`
- `schema-alias-support`

## Test Status

- 1,341 tests across 68 test files -- all passing
- Vitest test framework
- Zero TODO/FIXME/HACK comments in source code
