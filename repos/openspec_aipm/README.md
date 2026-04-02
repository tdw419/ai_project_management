# OpenSpec AIPM v3

Autonomous AI project manager built on OpenSpec.

## Architecture

```
OpenSpec (spec management)     <-- source of truth for specs
       |
  openspec-bridge.ts           <-- reads/writes specs via openspec CLI
       |
  scheduler.ts                 <-- orchestrates the loop
   /    |    \
  executor  model-router  prompt-builder
   |           |              |
  hermes    strategy       outcome-parser
 (agent)    selection      (SUCCESS/FAIL/NO_CHANGE)
```

## Key difference from v2

v2 (Python, 10K lines) reimplements spec parsing, task tracking, and
instruction generation in Python. v3 delegates all spec operations to
OpenSpec and only handles the execution layer.

What v3 does that's unique:
- Agent execution (run Hermes, capture output)
- Outcome parsing (git diff + test counts -> classification)
- Model routing (complexity -> local vs cloud)
- Prompt building (spec data -> agent instructions)
- Trust boundaries (protected files, git revert)

What v3 does NOT do (delegated to OpenSpec):
- Parse tasks.md / proposal.md
- Track task status
- Generate spec instructions
- Validate specs
- List/organize changes

## Usage

```bash
# Install dependencies
pnpm install

# Run single cycle
pnpm dev once

# Run continuously
pnpm dev run --interval 60

# Check status
pnpm dev status
```

## Configuration

See `aipm.yaml` for project configuration.
