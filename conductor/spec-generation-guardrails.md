# Plan: Robust Spec Generation Guardrails

The autonomous spec generation loop is structurally closed, but needs guardrails to be safe, token-efficient, and reliable. This plan implements robust JSON parsing, quality validation, and generation rate-limiting.

## 1. Robust JSON Extraction
Instead of relying on fragile regex for the first/last brace, we will enforce explicit markers in the agent prompt.

- **Markers**: `<|SPEC_JSON_START|>` and `<|SPEC_JSON_END|>`
- **Benefit**: Unambiguous extraction even if the agent explores a codebase full of JSON configuration files or provides verbose reasoning.

## 2. Quality & Integrity Gate
Implement a validation layer before any generated spec is written to disk.

- **Collision Check**: Verify the proposed `slug` doesn't already exist in `openspec/changes/`.
- **Structural Check**: Ensure the JSON contains all required fields (slug, title, summary, tasks).
- **Non-Empty Check**: Verify there is at least one phase/section and at least one implementation step.
- **Coherence**: Use the `OpenSpecBridge` to verify the project path is valid before writing.

## 3. Rate Limiting (Cooldown)
Prevent the system from burning tokens on repeated failures or redundant generations.

- **Cooldown Period**: Implement a 1-hour cooldown per project for spec generation.
- **Logic**: If a project is idle (no pending tasks), the scheduler will only trigger the `SpecGenerator` if at least 1 hour has passed since the last attempt.

## Implementation Steps

### Step 1: Refactor `SpecGenerator.ts`
- Update the agent prompt to include explicit JSON markers.
- Implement a robust parsing method that extracts content between markers.
- Add a `validateSpec` private method.

### Step 2: Update `Scheduler.ts`
- Add a `lastSpecGeneration` Map to track timestamps per project.
- Implement the cooldown check in the `runOnce` loop.

## Verification Plan

### Automated Verification
- Run a cycle on a mock project with no tasks to verify the cooldown triggers correctly.
- Verify that a malformed or empty JSON output from the agent is caught by the validation layer.

### Manual Verification
- Inspect the logs to ensure the `SpecGenerator` is only called once per hour when idle.
- Verify that generated `tasks.md` and `proposal.md` are correctly formatted and saved.
