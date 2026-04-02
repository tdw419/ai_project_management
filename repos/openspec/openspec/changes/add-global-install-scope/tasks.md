## 1. Global Config + Validation

- [x] 1.1 Add `installScope` (`global` | `project`) to `GlobalConfig` with explicit `global` default for newly created configs
- [x] 1.2 Update config schema validation and known-key checks to include install scope
- [x] 1.3 Add schema-evolution tests ensuring missing `installScope` in legacy configs resolves to effective `project` until explicit migration
- [x] 1.4 Extend `openspec config list` output to show install scope and source (`explicit`, `new-default`, `legacy-default`)

## 2. Tool Capability Metadata + Resolvers

- [x] 2.1 Extend `AI_TOOLS` metadata to declare scope support per surface (skills/commands)
- [x] 2.2 Add shared install-target resolver for skills and commands using requested scope + tool support
- [x] 2.3 Implement deterministic fallback/error behavior when preferred scope is unsupported, including default behavior when scope support metadata is absent
- [x] 2.4 Add unit tests for scope resolution (preferred, fallback, and hard-fail paths)

## 3. Command Generation Contract

- [x] 3.1 Update `ToolCommandAdapter` path contract to accept install context
- [x] 3.2 Update `generateCommand`/`generateCommands` to pass context through adapters
- [x] 3.3 Migrate all command adapters to the new path contract
- [x] 3.4 Update adapter tests for scoped path behavior (including Codex global path semantics)

## 4. Init Command Scope Support

- [x] 4.1 Add scope override flag to `openspec init` (`--scope global|project`)
- [x] 4.2 Resolve effective scope per tool/surface before writing artifacts
- [x] 4.3 Apply scope-aware generation/removal planning for skills and commands
- [x] 4.4 Surface effective scope decisions and fallback notes in init summary output
- [x] 4.5 Add init tests for global default, project override, and fallback/error scenarios

## 5. Update Command Scope Support

- [x] 5.1 Add scope override flag to `openspec update` (`--scope global|project`)
- [x] 5.2 Make configured-tool detection and drift checks scope-aware
- [x] 5.3 Persist and read last successful effective scope per tool/surface for deterministic scope-drift detection
- [x] 5.4 Apply scope-aware sync/removal with consistent fallback/error behavior
- [x] 5.5 Ensure scope changes update managed files in new targets and clean old managed targets safely
- [x] 5.6 Add update tests for global/project/fallback/error and repeat-run idempotency

## 6. Config UX

- [x] 6.1 Extend `openspec config profile` interactive flow to select install scope
- [x] 6.2 Preserve install scope when using preset shortcuts unless explicitly changed
- [x] 6.3 Ensure non-interactive config behavior remains deterministic with clear errors
- [x] 6.4 Add/adjust config command tests for install scope flows
- [x] 6.5 Add migration UX for legacy users to opt into `global` scope explicitly

## 7. Documentation

- [x] 7.1 Update `docs/supported-tools.md` with scope behavior and effective-scope fallback notes
- [x] 7.2 Update `docs/cli.md` examples for init/update scope options
- [x] 7.3 Document cross-project implications of global installs
- [x] 7.4 Add existing-user migration guide covering legacy-default behavior and explicit opt-in to `installScope: global`

## 8. Verification

- [x] 8.1 Run targeted tests for config, adapters, init, and update
- [x] 8.2 Run full test suite (`pnpm test`) and resolve regressions
- [x] 8.3 Manual smoke test: init/update with `installScope=global`
- [x] 8.4 Manual smoke test: init/update with `--scope project`
- [x] 8.5 Verify path resolution behavior on Windows CI (or cross-platform unit tests with mocked Windows paths)
- [x] 8.6 Verify combined behavior matrix for mixed tools across scope × delivery × command-surface capability
