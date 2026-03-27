# AIPM - AI Project Manager

> The foundational layer for AI-driven project development

## What is AIPM?

AIPM is a complete AI project management infrastructure that includes:

- **Prompt Management** - Queue, prioritize, analyze, and generate prompts
- **Project Management** - Projects, tasks, milestones, dependencies
- **CTRM** - Truth database with confidence scoring
- **ASCII World** - Visual shell for human oversight
- **API Server** - REST + WebSocket for real-time updates

## The Stack

```
┌─────────────────────────────────────────────────────────────┐
│                       AIPM STACK                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 4: Applications                                      │
│  ├── Geometry OS                                            │
│  ├── OpenClaw                                               │
│  └── Your AI Project                                        │
│           │                                                 │
│           ▼                                                 │
│  Layer 3: API & CLI                                         │
│  ├── REST endpoints                                         │
│  ├── WebSocket server                                       │
│  └── Command-line interface                                 │
│           │                                                 │
│           ▼                                                 │
│  Layer 2: Management                                        │
│  ├── Project Manager                                        │
│  ├── Prompt Engine                                          │
│  └── Response Analyzer                                      │
│           │                                                 │
│           ▼                                                 │
│  Layer 1: Core (CTRM + ASCII World)                        │
│  ├── Truth Database                                         │
│  ├── ASCII Parser/Renderer                                  │
│  └── Sync Server                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# From PyPI (future)
pip install aipm

# From source
git clone https://github.com/openclaw/aipm
cd aipm
pip install -e .
```

## Quick Start

```python
from aipm import ProjectManager, PromptEngine, Dashboard

# Initialize
pm = ProjectManager()
engine = PromptEngine()
dashboard = Dashboard()

# Create project
project = pm.create_project(
    name="My AI App",
    goal="Build an AI-powered application"
)

# Add tasks
pm.add_task(project.id, "Setup", "Initialize project structure", priority=1)
pm.add_task(project.id, "API", "Create REST API", priority=2)
pm.add_task(project.id, "Tests", "Write test suite", priority=3)

# Dashboard auto-updates
# → ~/.openclaw/workspace/.aipm/project_dashboard.ascii

# Queue ready tasks to CTRM
pm.queue_ready_tasks(project.id)

# Process prompts
engine.process_next()
```

## CLI Usage

```bash
# Start API server
aipm serve --port 8080

# Create project
aipm project create "My App" --goal "Build something amazing"

# Add task
aipm task add proj_abc123 "Implement feature" --priority 1

# Queue ready tasks
aipm queue ready --project proj_abc123

# Process next prompt
aipm process next

# View dashboard
aipm dashboard
```

## Architecture

### Core Modules

| Module | Purpose |
|--------|---------|
| `aipm.core` | Prompt engine, queue, analyzer, prioritizer |
| `aipm.ctrm` | Truth database and scoring |
| `aipm.ascii` | Visual shell and sync server |
| `aipm.project` | Project and task management |
| `aipm.api` | REST + WebSocket server |

### Key Features

**Prompt Management:**
- Multi-provider queue (GLM, Gemini, Claude, Local)
- Intelligent prioritization scoring
- Response quality analysis
- Template versioning

**Project Management:**
- Projects with goals and milestones
- Tasks with dependencies
- Build/test integration
- Completion tracking

**CTRM:**
- Truth database (SQLite)
- CAAMG scoring (Coherent, Authentic, Actionable, Meaningful, Grounded)
- 2,400+ prompts queued

**ASCII World:**
- ASCII dashboards for human oversight
- Hash verification for authenticity
- WebSocket sync for real-time updates
- HTML renderer

## The Self-Referential Loop

```
You ──► AI ──► AIPM ──► Better AIPM
              │              │
              │              │
              └──────────────┘
              (self-improving)
```

AIPM can improve itself while using it to build other projects. This is the key insight: **the prompt management system is itself a project that the AI can improve.**

## Documentation

- [Getting Started](docs/getting_started.md)
- [API Reference](docs/api_reference.md)
- [Architecture](docs/architecture.md)

## License

MIT

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

## Links

- Homepage: https://github.com/openclaw/aipm
- Documentation: https://aipm.readthedocs.io
- OpenClaw: https://openclaw.ai
