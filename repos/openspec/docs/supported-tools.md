# Supported Tools

OpenSpec works with many AI coding assistants. When you run `openspec init`, OpenSpec configures selected tools using your active profile/workflow selection and delivery mode.

## How It Works

For each selected tool, OpenSpec can install:

1. **Skills** (if delivery includes skills): `.../skills/openspec-*/SKILL.md`
2. **Commands** (if delivery includes commands): tool-specific `opsx-*` command files

By default, OpenSpec uses the `core` profile, which includes:
- `propose`
- `explore`
- `apply`
- `archive`

You can enable expanded workflows (`new`, `continue`, `ff`, `verify`, `sync`, `bulk-archive`, `onboard`) via `openspec config profile`, then run `openspec update`.

## Tool Directory Reference

| Tool (ID) | Skills path pattern | Command path pattern |
|-----------|---------------------|----------------------|
| Amazon Q Developer (`amazon-q`) | `.amazonq/skills/openspec-*/SKILL.md` | `.amazonq/prompts/opsx-<id>.md` |
| Antigravity (`antigravity`) | `.agent/skills/openspec-*/SKILL.md` | `.agent/workflows/opsx-<id>.md` |
| Auggie (`auggie`) | `.augment/skills/openspec-*/SKILL.md` | `.augment/commands/opsx-<id>.md` |
| Claude Code (`claude`) | `.claude/skills/openspec-*/SKILL.md` | `.claude/commands/opsx/<id>.md` |
| Cline (`cline`) | `.cline/skills/openspec-*/SKILL.md` | `.clinerules/workflows/opsx-<id>.md` |
| CodeBuddy (`codebuddy`) | `.codebuddy/skills/openspec-*/SKILL.md` | `.codebuddy/commands/opsx/<id>.md` |
| Codex (`codex`) | `.codex/skills/openspec-*/SKILL.md` | `$CODEX_HOME/prompts/opsx-<id>.md`\* |
| Continue (`continue`) | `.continue/skills/openspec-*/SKILL.md` | `.continue/prompts/opsx-<id>.prompt` |
| CoStrict (`costrict`) | `.cospec/skills/openspec-*/SKILL.md` | `.cospec/openspec/commands/opsx-<id>.md` |
| Crush (`crush`) | `.crush/skills/openspec-*/SKILL.md` | `.crush/commands/opsx/<id>.md` |
| Cursor (`cursor`) | `.cursor/skills/openspec-*/SKILL.md` | `.cursor/commands/opsx-<id>.md` |
| Factory Droid (`factory`) | `.factory/skills/openspec-*/SKILL.md` | `.factory/commands/opsx-<id>.md` |
| Gemini CLI (`gemini`) | `.gemini/skills/openspec-*/SKILL.md` | `.gemini/commands/opsx/<id>.toml` |
| GitHub Copilot (`github-copilot`) | `.github/skills/openspec-*/SKILL.md` | `.github/prompts/opsx-<id>.prompt.md`\*\* |
| iFlow (`iflow`) | `.iflow/skills/openspec-*/SKILL.md` | `.iflow/commands/opsx-<id>.md` |
| Kilo Code (`kilocode`) | `.kilocode/skills/openspec-*/SKILL.md` | `.kilocode/workflows/opsx-<id>.md` |
| Kiro (`kiro`) | `.kiro/skills/openspec-*/SKILL.md` | `.kiro/prompts/opsx-<id>.prompt.md` |
| OpenCode (`opencode`) | `.opencode/skills/openspec-*/SKILL.md` | `.opencode/commands/opsx-<id>.md` |
| Pi (`pi`) | `.pi/skills/openspec-*/SKILL.md` | `.pi/prompts/opsx-<id>.md` |
| Qoder (`qoder`) | `.qoder/skills/openspec-*/SKILL.md` | `.qoder/commands/opsx/<id>.md` |
| Qwen Code (`qwen`) | `.qwen/skills/openspec-*/SKILL.md` | `.qwen/commands/opsx-<id>.toml` |
| RooCode (`roocode`) | `.roo/skills/openspec-*/SKILL.md` | `.roo/commands/opsx-<id>.md` |
| Trae (`trae`) | `.trae/skills/openspec-*/SKILL.md` | Not generated (no command adapter; use skill-based `/openspec-*` invocations) |
| Windsurf (`windsurf`) | `.windsurf/skills/openspec-*/SKILL.md` | `.windsurf/workflows/opsx-<id>.md` |

\* Codex commands are installed in the global Codex home (`$CODEX_HOME/prompts/` if set, otherwise `~/.codex/prompts/`), not your project directory.

\*\* GitHub Copilot prompt files are recognized as custom slash commands in IDE extensions (VS Code, JetBrains, Visual Studio). Copilot CLI does not currently consume `.github/prompts/*.prompt.md` directly.

## Install Scope

OpenSpec supports two install scopes that control where tool artifacts (skills and commands) are written:

| Scope | Skills location | Commands location |
|-------|----------------|-------------------|
| `project` | `<project>/.tool/skills/openspec-*/SKILL.md` | `<project>/.tool/commands/opsx-<id>.md` |
| `global` | `<project>/.tool/skills/openspec-*/SKILL.md` | `<user-dir>/opsx-<id>.md` (tool-dependent) |

### Setting the install scope

```bash
# Interactive: choose via config wizard
openspec config profile
# → select "Install scope"

# Direct: set via config key
openspec config set installScope global
openspec config set installScope project

# View current scope
openspec config list
```

### Effective-scope fallback

Not every tool supports both scopes for every surface. OpenSpec resolves the **effective scope** per tool and surface (skills/commands) using this logic:

1. **Try preferred scope.** If your `installScope` setting is `global` and the tool supports global for that surface, it is used.
2. **Fallback to alternate.** If the preferred scope is unsupported, OpenSpec falls back to the other scope automatically and logs a note.
3. **Hard fail.** If a tool supports neither scope for a surface, an error is raised.

The table below shows current scope support by tool:

| Tool | Skills scopes | Commands scopes |
|------|--------------|-----------------|
| Codex | `project` only | `global`, `project` |
| All others | `project` only | `project` only |

> **Note:** Codex is the only tool with explicit global commands support today. Its commands install to `$CODEX_HOME/prompts/` (or `~/.codex/prompts/`) regardless of scope setting. For all other tools, both surfaces default to project-local paths. Additional tools may gain global support in future releases.

When you run `openspec init` or `openspec update`, the scope resolver evaluates each selected tool and reports any fallbacks in the output. You can inspect the resolved scope with `openspec config list`, which annotates the source:

```
Install scope:
  installScope: global (explicit)
```

The annotation indicates how the value was determined:
- `(explicit)` — set by you via `openspec config set`
- `(new-default)` — new installation; no config file existed, so the built-in default (`global`) was used
- `(legacy-default)` — existing config file predates installScope; effective value is `project`

---

## Non-Interactive Setup

For CI/CD or scripted setup, use `--tools` (and optionally `--profile`):

```bash
# Configure specific tools
openspec init --tools claude,cursor

# Configure all supported tools
openspec init --tools all

# Skip tool configuration
openspec init --tools none

# Override profile for this init run
openspec init --profile core
```

**Available tool IDs (`--tools`):** `amazon-q`, `antigravity`, `auggie`, `claude`, `cline`, `codex`, `codebuddy`, `continue`, `costrict`, `crush`, `cursor`, `factory`, `gemini`, `github-copilot`, `iflow`, `kilocode`, `kiro`, `opencode`, `pi`, `qoder`, `qwen`, `roocode`, `trae`, `windsurf`

## Workflow-Dependent Installation

OpenSpec installs workflow artifacts based on selected workflows:

- **Core profile (default):** `propose`, `explore`, `apply`, `archive`
- **Custom selection:** any subset of all workflow IDs:
  `propose`, `explore`, `new`, `continue`, `apply`, `ff`, `sync`, `archive`, `bulk-archive`, `verify`, `onboard`

In other words, skill/command counts are profile-dependent and delivery-dependent, not fixed.

## Generated Skill Names

When selected by profile/workflow config, OpenSpec generates these skills:

- `openspec-propose`
- `openspec-explore`
- `openspec-new-change`
- `openspec-continue-change`
- `openspec-apply-change`
- `openspec-ff-change`
- `openspec-sync-specs`
- `openspec-archive-change`
- `openspec-bulk-archive-change`
- `openspec-verify-change`
- `openspec-onboard`

See [Commands](commands.md) for command behavior and [CLI](cli.md) for `init`/`update` options.

## Command Surface Capabilities

Not all tools expose OpenSpec workflows the same way. OpenSpec classifies each tool's **command surface** — how it makes workflows invocable — into one of three categories:

| Surface | Meaning | Example tools |
|---------|---------|---------------|
| `adapter` | Command files generated through a registered command adapter | Claude Code, Cursor, Gemini CLI, and most other tools |
| `skills-invocable` | Skills are directly invocable as commands (e.g. skill entry points like `/openspec-new-change`) | Trae |
| `none` | No command surface available — incompatible with `delivery=commands` | (any future tool without adapter or skills) |

### How the surface is resolved

For each tool, OpenSpec resolves the command surface using this priority:

1. **Explicit override** — a `commandSurface` field in the tool's metadata (e.g. Trae is explicitly set to `skills-invocable`)
2. **Adapter presence** — if the tool has a registered command adapter, it resolves to `adapter`
3. **Skills directory only** — if the tool has a `skillsDir` but no adapter, it resolves to `skills-invocable`
4. **Neither** — resolves to `none`

### Delivery mode interactions

The command surface determines what happens under each delivery mode:

| Delivery mode | `adapter` | `skills-invocable` | `none` |
|---------------|-----------|--------------------|--------|
| `both` | Skills + commands generated | Skills generated (no adapter commands) | No artifacts; compatibility warning |
| `skills` | Skills generated; commands removed | Skills generated | No artifacts; compatibility warning |
| `commands` | Commands generated; skills removed | **Skills retained as command surface** | **Error — fail fast** |

**Key behavior for `skills-invocable` tools under `delivery=commands`:** Since these tools invoke workflows through skill entries (not adapter-generated command files), OpenSpec keeps or generates skills even when delivery is set to commands-only. This ensures tools like Trae always have invocable workflow artifacts. You'll see a note in the output:

```
Note: Skills retained as command surface for: trae (delivery=commands, command surface: skills-invocable)
```

### Trae specifics

Trae does not have a command adapter. Instead, it invokes OpenSpec workflows via skill entries (e.g. `/openspec-new-change`, `/openspec-explore`). This means:

- Skills **must** be present for Trae to function, regardless of delivery mode
- `delivery=commands` will not remove Trae's skills — they *are* the command surface
- There is no command file column for Trae in the tool directory reference above

## Related

- [CLI Reference](cli.md) — Terminal commands
- [Commands](commands.md) — Slash commands and skills
- [Getting Started](getting-started.md) — First-time setup
