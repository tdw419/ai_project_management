# How AIPM Works

**AI Project Management** - A self-sustaining prompt management system for AI-driven development.

---

## Overview

AIPM is a system that manages a queue of prompts, processes them through LLMs, and generates follow-up prompts based on results. It's designed to run autonomously, continuously improving your codebase.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AIPM ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐              │
│   │   PROMPTS   │────▶│  PRIORITIZE │────▶│   PROCESS   │              │
│   │   (Queue)   │     │  (Scoring)  │     │   (LLM)     │              │
│   └─────────────┘     └─────────────┘     └──────┬──────┘              │
│          ▲                                        │                     │
│          │                                        ▼                     │
│   ┌──────┴──────┐                          ┌─────────────┐              │
│   │   GENERATE  │◀─────────────────────────│   ANALYZE   │              │
│   │ (Follow-ups)│                          │  (Quality)  │              │
│   └─────────────┘                          └─────────────┘              │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────┐          │
│   │                    CTRM DATABASE                         │          │
│   │   (Truths + Prompts + Projects + Results)               │          │
│   └─────────────────────────────────────────────────────────┘          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Prompt Queue (CTRM Database)

All prompts are stored in a SQLite database (`data/truths.db`) with CTRM scoring.

**Table: `prompt_queue`**

| Field | Type | Description |
|-------|------|-------------|
| `id` | TEXT | Unique prompt ID |
| `prompt` | TEXT | The prompt text |
| `priority` | INTEGER | 1-10 (1 = highest) |
| `status` | TEXT | pending/processing/completed/failed |
| `ctrm_confidence` | REAL | Overall quality score (0-1) |
| `result` | TEXT | LLM response |
| `queued_at` | TEXT | Timestamp |

**CTRM Scoring** (Contextual Truth Reference Model):
- **Coherent** - Is the prompt logically consistent?
- **Authentic** - Is it genuine and not synthetic?
- **Actionable** - Can it be executed?
- **Meaningful** - Does it add value?
- **Grounded** - Is it based on reality?

```python
from aipm import get_aipm

aipm = get_aipm()

# Add a prompt
prompt_id = aipm.enqueue("Write a function to parse JSON")

# Get next prompt
prompts = aipm.ctrm.dequeue(limit=1)
```

---

### 2. Prompt Prioritizer

Determines which prompt to process next using a scoring formula:

```
score = (5.0 / priority) + (confidence × 3.0) + age_bonus + (impact × 1.5)
```

**Factors:**
- **Priority** - Urgency (lower number = higher priority)
- **Confidence** - CTRM quality score
- **Age** - Fresh prompts get bonus, stale get penalty
- **Impact** - Expected value of the result

```python
from aipm.core.prompt_prioritizer import PromptPrioritizer

prioritizer = PromptPrioritizer()

# Get top 10 prompts by score
scored = prioritizer.get_next_prompt(limit=10)

for prompt, score in scored:
    print(f"[{score:.2f}] {prompt['prompt'][:60]}...")
```

---

### 3. LLM Providers

AIPM supports multiple LLM backends:

#### A. LM Studio (Local)

```python
from aipm.core.simple_bridge import SimpleQueueBridge

bridge = SimpleQueueBridge()

# Process a prompt
result = await bridge.process_chat(
    messages=[
        {"role": "user", "content": "Write a hello world"}
    ],
    model="qwen2.5-coder-7b-instruct",
)
```

#### B. Pi Agent (Coding Agent)

```python
from aipm.core.extended_providers import PiAgentProvider, PiAgentConfig

provider = PiAgentProvider(PiAgentConfig(
    repo_path="/path/to/project",
    default_model="zai/glm-5",
))

result = await provider.execute_task(
    task="Implement a REST API endpoint",
    model="zai/glm-5",
)
```

#### C. ZAI Cloud (z.ai)

```python
from aipm.core.extended_providers import ZAIProvider, ZAIConfig

provider = ZAIProvider(ZAIConfig(
    api_key="your-api-key",
    model="glm-4-plus",
))

result = await provider.process_chat(
    messages=[{"role": "user", "content": "..."}]
)
```

---

### 4. Response Analyzer

Analyzes LLM responses for quality:

```python
from aipm.core.response_analyzer import PromptResponseAnalyzer

analyzer = PromptResponseAnalyzer()
analysis = analyzer.analyze_response(prompt_id)

print(f"Quality: {analysis.quality}")  # COMPLETE/PARTIAL/FAILED/NEEDS_REVIEW
print(f"Confidence: {analysis.confidence:.0%}")

if analysis.needs_followup:
    print(f"Follow-up needed: {analysis.followup_reason}")
```

**Quality Levels:**
- `COMPLETE` - Fully addressed the prompt
- `PARTIAL` - Partially addressed, needs more work
- `FAILED` - Did not address the prompt
- `NEEDS_REVIEW` - Needs human review

---

### 5. Prompt Generator

Generates follow-up prompts from results:

```python
from aipm.core.prompt_prioritizer import PromptGenerator

generator = PromptGenerator()

# Generate from a result
new_prompts = generator.generate_from_results(
    original_prompt="Write a function to parse JSON",
    result="Here's the implementation...",
)

# Generate from gaps (missing coverage)
gap_prompts = generator.generate_from_gaps()
```

---

### 6. ASCII World Dashboard

Visual dashboards for monitoring:

```
╔══════════════════════════════════════════════════════════════════════╗
║                  AIPM CONTINUOUS PROCESSING                           ║
║                  Updated: 2026-03-27 07:00:00                         ║
╚══════════════════════════════════════════════════════════════════════╝

📊 Statistics:
   Processed: 589
   Errors: 3
   Model: qwen2.5-coder-7b-instruct

📦 OpenMind: [████████████░░░░░░░░] 62.5%
📦 Geometry OS: [████████████████░░] 85.0%

📝 Queue: 11,400 pending | 589 completed
```

---

## The Processing Loop

### Closed-Loop Cycle

```
DEQUEUE → PROCESS → ANALYZE → GENERATE → ENQUEUE → [REPEAT]
```

### Continuous Loop

The `continuous_loop.py` script runs this cycle forever:

```bash
# Start the loop
./loop.sh start

# Start with Pi agent
./loop.sh start --pi

# Check status
./loop.sh status

# View logs
./loop.sh logs

# Stop
./loop.sh stop
```

### Automated Loop (Python)

```python
from aipm.core.automated_loop import AutomatedPromptLoop

loop = AutomatedPromptLoop()

# Run once
await loop.run_once()

# Run forever
await loop.run_forever(interval_seconds=60)
```

---

## AutoSpec Integration

AIPM includes AutoSpec for experiment tracking. When LLM responses contain hypotheses in H/T/M/B format, they're automatically tested:

```
H: Increase core gravity by 0.1
T: shaders/radial_drift.wgsl
M: legibility.clarity > 0.9
B: 5
```

**Parsing:**
- `H:` - Hypothesis description
- `T:` - Target file to modify
- `M:` - Metric to measure
- `B:` - Budget (max attempts)

**Results logged to `results.tsv`:**

```
hash      metric  decision  description
9fe22465  3.12    discard   Increase core gravity - No improvement
```

---

## Project Management

AIPM tracks projects and tasks:

```python
from aipm import get_aipm

aipm = get_aipm()

# Create a project
project = aipm.create_project(
    name="My App",
    goal="Build a web application",
    path="/path/to/project",
)

# Add tasks
aipm.projects.add_task(
    project_id=project.id,
    name="Design API",
    description="Design REST API endpoints",
)

# List projects
for p in aipm.list_projects():
    stats = aipm.projects.get_project_stats(p.id)
    print(f"{p.name}: {stats['completion_percentage']:.1f}%")
```

---

## CLI Commands

```bash
# Install
pip install -e .

# CLI
aipm --help

# Create project
aipm project create -n "My Project" -g "Build something"

# Add prompt
aipm prompt "Write code for X" -p 1

# Process next
aipm process next

# Show status
aipm status

# Start API server
aipm serve --port 8080
```

---

## Configuration

**`src/aipm/config.py`:**

```python
# Default models
DEFAULT_VISION_MODEL = "qwen/qwen3-vl-8b"
DEFAULT_REASONING_MODEL = "qwen2.5-coder-7b-instruct"
DEFAULT_CODE_MODEL = "qwen2.5-coder-7b-instruct"
DEFAULT_PI_MODEL = "zai/glm-5"

# LM Studio URL
LM_STUDIO_URL = "http://localhost:1234"

# Database paths
CTRM_DB = DATA_DIR / "truths.db"
QUEUE_DB = DATA_DIR / "queue.db"
PROJECTS_DB = DATA_DIR / "projects.db"
```

---

## API Server

REST + WebSocket API for integration:

```bash
# Start server
aipm serve --port 8080
```

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prompts` | List prompts |
| POST | `/api/prompts` | Create prompt |
| GET | `/api/prompts/{id}` | Get prompt |
| POST | `/api/prompts/{id}/process` | Process prompt |
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create project |
| GET | `/api/stats` | Get statistics |
| WS | `/ws` | WebSocket for real-time updates |

---

## File Structure

```
aipm/
├── src/aipm/
│   ├── __init__.py              # Main exports
│   ├── config.py                # Configuration
│   ├── cli.py                   # CLI commands
│   ├── integration.py           # Main AIPM class
│   │
│   ├── core/
│   │   ├── engine.py            # Prompt engine
│   │   ├── queue.py             # Queue management
│   │   ├── prioritizer.py       # Scoring
│   │   ├── prompt_prioritizer.py # Enhanced prioritization
│   │   ├── simple_bridge.py     # LM Studio bridge
│   │   ├── extended_providers.py # Pi/ZAI providers
│   │   ├── response_analyzer.py  # Quality analysis
│   │   ├── automated_loop.py     # Autonomous loop
│   │   └── ctrm_prompt_manager.py # CTRM integration
│   │
│   ├── ctrm/
│   │   └── database.py          # Truth database
│   │
│   ├── project/
│   │   └── manager.py           # Project management
│   │
│   ├── ascii_world/
│   │   └── dashboard.py         # ASCII dashboards
│   │
│   └── api/
│       └── server.py            # REST/WebSocket API
│
├── vendor/
│   └── autospec/                # Vendored AutoSpec
│
├── data/
│   ├── truths.db                # CTRM database
│   ├── queue.db                 # Queue database
│   └── projects.db              # Projects database
│
├── continuous_loop.py           # Main loop script
├── loop.sh                      # Loop control script
└── pyproject.toml               # Package config
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/tdw419/ai_project_management.git
cd ai_project_management/aipm

# Install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Start LM Studio with a model loaded
# (or use --pi flag for Pi agent)

# Run the loop
./loop.sh start

# Check status
./loop.sh status

# View logs
./loop.sh logs
```

---

## Models Reference

| Model | Use Case | Provider |
|-------|----------|----------|
| `qwen2.5-coder-7b-instruct` | Fast iteration, code | LM Studio |
| `qwen/qwen3-coder-30b` | Complex reasoning | LM Studio |
| `qwen/qwen3-vl-8b` | Vision tasks | LM Studio |
| `zai/glm-5` | Pi agent default | Pi Agent |
| `glm-4-plus` | Cloud reasoning | ZAI Cloud |

---

## Troubleshooting

### No model loaded

```
❌ No model available. Please load a model in LM Studio first:
   1. Open LM Studio
   2. Load model: qwen2.5-coder-7b-instruct
   3. Restart this script
```

**Solution:** Open LM Studio and load a model, or use `--pi` flag.

### Connection refused

```
❌ Error: Connection refused to localhost:1234
```

**Solution:** Ensure LM Studio is running with the server enabled.

### Database locked

```
❌ Error: database is locked
```

**Solution:** Only one loop can run at a time. Stop any existing loops.

---

## Related Projects

- **Ouroboros** - Self-evolving code system with AutoSpec
- **Geometry OS** - AI-built OS for AIs
- **OpenMind** - Attention visualization

---

*Last updated: 2026-03-27*
