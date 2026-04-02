## 0. Stacking Coordination

- [x] 0.1 Rebase this change on latest `main` before implementation
- [x] 0.2 If `simplify-skill-installation` is merged first, preserve its profile/delivery model and apply this change as a capability-aware refinement
- [x] 0.3 If this change merges first, ensure follow-up rebases do not reintroduce a blanket "commands = remove all skills" rule
- [x] 0.4 If `add-global-install-scope` is merged, verify combined scope × delivery × command-surface behavior remains deterministic

## 1. Tool Command-Surface Capability Model

- [x] 1.1 Extend tool metadata in `src/core/config.ts` with an optional command-surface capability field
- [x] 1.2 Define supported capability values: `adapter`, `skills-invocable`, `none`
- [x] 1.3 Mark Trae as `skills-invocable`
- [x] 1.4 Add a shared capability resolver (explicit metadata override first, inferred fallback from adapter presence second)
- [x] 1.5 Add focused unit tests for capability resolution (explicit override, inferred adapter, inferred none)

## 2. Init: Capability-Aware Delivery Planning

- [x] 2.1 Refactor init generation logic to compute per-tool effective actions (generate/remove skills and commands) instead of using only global booleans
- [x] 2.2 In `delivery=commands`, keep/generate skills for `skills-invocable` tools and do not remove those managed skill directories
- [x] 2.3 In `delivery=commands`, fail fast before writes when any selected tool resolves to `none`
- [x] 2.4 Update init output to clearly report effective behavior for `skills-invocable` tools (skills used as command surface)
- [x] 2.5 Ensure init no longer reports "no adapter" for tools intentionally using `skills-invocable`
- [x] 2.6 Add/adjust init tests for `delivery=commands` + `trae` (skills retained/generated, no adapter error), mixed tools (`claude,trae`) with per-tool expected outputs, and deterministic failure path for unsupported command surface (`none`)

## 3. Update: Capability-Aware Sync and Drift Detection

- [x] 3.1 Refactor update sync logic to apply delivery behavior per tool capability (not globally per run)
- [x] 3.2 In `delivery=commands`, keep/generate managed skills for `skills-invocable` tools
- [x] 3.3 In `delivery=commands`, fail before partial updates when configured tools include a `none` command surface
- [x] 3.4 Update profile/delivery drift detection to avoid perpetual drift for `skills-invocable` tools under commands delivery
- [x] 3.5 Ensure configured-tool detection still includes `skills-invocable` tools under commands delivery when managed skills exist
- [x] 3.6 Update summary output so skills-invocable behavior is reported as expected behavior (not implicit skip/error)
- [x] 3.7 Add/adjust update tests for `delivery=commands` + configured Trae (skills retained/generated), idempotent second update (no false drift loop), mixed configured tools (`claude` + `trae`), and deterministic preflight failure for unsupported command surface (`none`)

## 4. UX and Error Messaging

- [x] 4.1 Add interactive init compatibility note for `delivery=commands` when selected tools include `skills-invocable`
- [x] 4.2 Add deterministic non-interactive error text with incompatible tool IDs and suggested alternatives (`both` or `skills`)
- [x] 4.3 Align init and update wording so capability-related behavior/messages are consistent

## 5. Documentation Updates

- [x] 5.1 Update `docs/supported-tools.md` to document command-surface semantics for Trae and clarify delivery interactions
- [x] 5.2 Update `docs/cli.md` delivery guidance to explain capability-aware behavior for `delivery=commands`
- [x] 5.3 Add a short troubleshooting note for "commands-only + unsupported tool" failures

## 6. Verification

- [x] 6.1 Run targeted tests: `test/core/init.test.ts` and `test/core/update.test.ts`
- [x] 6.2 Run any new capability/unit test files added in this change
- [x] 6.3 Run full test suite (`pnpm test`) and resolve regressions
- [x] 6.4 Manual smoke check: `openspec init --tools trae` with `delivery=commands`
- [x] 6.5 Manual smoke check: mixed tools (`claude,trae`) with `delivery=commands`
