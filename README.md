# AIPM - AI Project Manager

> The foundation for AI-driven development

AIPM is a complete AI project management infrastructure that provides:

- **Prompt Management** - Intelligent prioritization, multi-provider routing
- **CTRM** - Contextual Truth Reference Model for knowledge storage
- **ASCII World** - Visual dashboards with real-time updates
- **Project Management** - Tasks, dependencies, milestones
- **API** - REST + WebSocket for integration

## The Self-Referential Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE AIPM WORKFLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  YOU ──► AI (OpenClaw/Gemini) ──► AIPM System                  │
│                                     │                           │
│                                     ▼                           │
│                          ┌─────────────────┐                    │
│                          │ Project Manager │                    │
│                          └────────┬────────┘                    │
│                                   │                             │
│                                   ▼                             │
│                          ┌─────────────────┐                    │
│                          │  Prompt Engine  │                    │
│                          └────────┬────────┘                    │
│                                   │                             │
│                                   ▼                             │
│                          ┌─────────────────┐                    │
│                          │  ASCII Dashboard │ ◄── YOU SEE IT   │
│                          └────────┬────────┘                    │
│                                   │                             │
│                                   ▼                             │
│                          PROJECT BUILT                         │
│                          (with improved tools)                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# From source
git clone https://github.com/tdw419/aipm.git
cd aipm
pip install -e .

# Or directly
pip install aipm
```

## Quick Start

```python
from aipm import PromptSystem, ProjectManager, Dashboard

# Initialize
system = PromptSystem()
pm = ProjectManager()
dashboard = Dashboard()

# Create a project
project = pm.create_project(
    name="My App",
    goal="Build a web application",
    path="/path/to/project"
)

# Add tasks
pm.add_task(
    project_id=project.id,
    name="Implement API",
    description="Create REST API endpoints",
    priority=1
)

# Process prompts
result = system.process_next()
print(result)

# View dashboard
dashboard.serve(port=8080)
```

## CLI Usage

```bash
# Start the API server
aipm serve --port 8080

# Create a project
aipm project create "My App" --goal "Build something" --path ./myapp

# Add tasks
aipm task add proj_abc123 "Implement feature X" --priority 1

# Process prompts
aipm process next
aipm process forever --interval 60

# View status
aipm status
```

## Architecture

```
aipm/
├── core/           # Prompt engine, queue, analyzer, prioritizer
├── ctrm/           # Truth database, scoring, models
├── ascii_world/    # Visual shell, sync server, renderer
├── project/        # Project/task management, dependencies
└── api/            # REST + WebSocket server
```

## The Closed-Loop Cycle

```
DEQUEUE → PROCESS → ANALYZE → GENERATE → ENQUEUE → [LOOP]
    │                                           │
    └───────────────────────────────────────────┘
```

1. **DEQUEUE** - Get highest-priority prompt
2. **PROCESS** - Execute via LLM
3. **ANALYZE** - Determine quality (COMPLETE/PARTIAL/FAILED)
4. **GENERATE** - Create follow-up prompts
5. **ENQUEUE** - Add to queue with adjusted priorities

## Features

### Prompt Prioritization

```python
score = (5.0 / priority) + (confidence × 3.0) + age_bonus + (impact × 1.5)
```

### Quality Assessment

| Icon | Quality | Meaning |
|------|---------|---------|
| ✅ | COMPLETE | Task fully achieved |
| ◐ | PARTIAL | Progress made, more needed |
| ❌ | FAILED | Task crashed or aborted |
| 🔍 | NEEDS_REVIEW | Done but needs verification |

### ASCII World Integration

Every action is reflected in ASCII for human oversight:

```
AI creates project → SQLite updated → ASCII dashboard → WebSocket → You see it
```

## License

MIT
