# AI Agent Guidelines

This file provides guidelines for AI agents (pi, codex, etc.) working on this project.

## Principles
- Follow the spec-driven development process
- Make small, incremental changes
- Run tests before and after changes
- Document decisions in the spec
- DO NOT modify protected files listed in project.yaml

## Workflow
1. Read the current task from `openspec/changes/<change-id>/tasks.md`
2. Review requirements in `requirements.md` and design in `design.md`
3. Implement the task, touching only the files listed in the task
4. Run tests to verify nothing is broken
5. Commit with message referencing the task ID (e.g., `TASK-01: implement X`)

## Spec Structure
```
openspec/
  changes/
    <change-id>/
      status.yaml        # Change status (draft/proposed/approved/in-progress/completed)
      proposal.md        # Why + what
      requirements.md    # Formal requirements (MUST/SHALL/SHOULD/MAY)
      design.md          # Architecture, components, file changes
      tasks.md           # Implementation tasks with steps
```

## Labels
- `spec-defined` -- Spec is complete, ready for implementation
- `in-progress` -- Currently being worked on
- `needs-verification` -- Code written, needs test verification
- `blocked` -- Blocked by dependency
- `circuit-breaker` -- Auto-paused by AIPM due to failures
