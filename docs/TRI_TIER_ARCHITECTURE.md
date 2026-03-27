# Tri-Tier Intelligence Architecture

## Overview

AIPM now supports distributed intelligence across three tiers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRI-TIER INTELLIGENCE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  TIER 1: ORCHESTRATOR (AIPM Core)                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  • Management & Prioritization                                   │   │
│  │  • Truth Scoring (CTRM)                                          │   │
│  │  • Project Coordination                                          │   │
│  │  • Substrate: Local Python/SQLite                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  TIER 2: EXECUTIVE BODY (Pi Agent)                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  • Complex Task Execution                                        │   │
│  │  • PR Generation                                                 │   │
│  │  • Parallel Experiments                                          │   │
│  │  • Substrate: apps/pi/ (monorepo)                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  TIER 3: SUPER-CORTEX (z.ai Cloud)                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  • Massive Reasoning                                             │   │
│  │  • Deep Code Refactoring                                         │   │
│  │  • Architectural Decisions                                       │   │
│  │  • Substrate: High-performance Cloud API                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Provider Selection

| Task Type | Provider | Reason |
|-----------|----------|--------|
| Quick iteration | Local (LM Studio) | Speed |
| Implementation | Pi Agent | Execution capability |
| Architecture | z.ai Cloud | Creative depth |
| Refactoring | z.ai Cloud | Complex reasoning |
| Prototyping | Local + Pi | Speed + execution |

## Complexity Scoring

```python
def score_complexity(prompt: str) -> float:
    """
    0.0-0.3  → Local (fast)
    0.3-0.5  → Local or Pi (implementation)
    0.5-1.0  → Cloud (deep reasoning)
    """
```

Indicators:
- "architect" → +0.3
- "refactor" → +0.25
- "redesign" → +0.3
- "optimize" → +0.2
- "implement" → +0.15

## Configuration

### z.ai Cloud

```python
from aipm.core.extended_providers import ZAIProvider, ZAIConfig

config = ZAIConfig(
    api_key="your-api-key",
    model="glm-4-plus",  # or "glm-4-flash"
)

zai = ZAIProvider(config)
result = await zai.process_chat(messages)
```

### Pi Agent

```python
from aipm.core.extended_providers import PiAgentProvider, PiAgentConfig

config = PiAgentConfig(
    repo_path="/path/to/pi/agent",
)

pi = PiAgentProvider(config)
result = await pi.execute_task("Implement feature X")
```

### Hybrid Router

```python
from aipm.core.extended_providers import HybridRouter

router = HybridRouter(
    local_provider=local_bridge,
    cloud_provider=zai,
    pi_provider=pi,
)

# Automatically selects best provider
result = await router.process(prompt)
```

## Self-Improvement Loop

AIPM can now improve itself using this architecture:

```
┌─────────────────────────────────────────────────────────────┐
│  1. AIPM identifies improvement opportunity                 │
│     └─► CTRM analysis shows gap in provider routing         │
│                                                             │
│  2. Route to z.ai for architectural design                  │
│     └─► "Design better provider selection algorithm"        │
│                                                             │
│  3. Route to Pi Agent for implementation                    │
│     └─► "Implement the new HybridRouter class"              │
│                                                             │
│  4. AIPM tests and validates                                │
│     └─► ResponseAnalyzer checks quality                     │
│                                                             │
│  5. AIPM integrates improvement                             │
│     └─► Git commit + update CTRM                            │
│                                                             │
│  6. Loop repeats                                            │
│     └─► System gets smarter                                 │
└─────────────────────────────────────────────────────────────┘
```

## Projects Using This Architecture

| Project | Primary Tier | Support Tier |
|---------|--------------|--------------|
| OpenMind | Local | z.ai (complex viz) |
| Neuro-Spatial Fusion | All three | Full stack |
| AIPM Self-Improvement | z.ai | Pi Agent |

## Future Enhancements

1. **Cost Optimization**: Track token usage, auto-switch to cheaper providers
2. **Latency Tracking**: Learn which provider is fastest for which task type
3. **Quality Learning**: Feed ResponseAnalyzer results back into routing
4. **Parallel Execution**: Run same prompt on multiple providers, pick best
