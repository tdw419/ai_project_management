"""
AIPM Configuration
"""

from pathlib import Path

# Default paths
PACKAGE_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
CTRM_DB = DATA_DIR / "truths.db"
QUEUE_DB = DATA_DIR / "queue.db"
PROJECTS_DB = DATA_DIR / "projects.db"
ASCII_WORLD_DIR = PACKAGE_ROOT / "ascii_world"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Provider configuration
DEFAULT_PROVIDER = "lm_studio"
LM_STUDIO_URL = "http://localhost:1234"

# Default models
DEFAULT_VISION_MODEL = "qwen/qwen3-vl-8b"
DEFAULT_REASONING_MODEL = "qwen2.5-coder-7b-instruct"
DEFAULT_CODE_MODEL = "qwen2.5-coder-7b-instruct"
DEFAULT_CHAT_MODEL = "qwen/qwen3.5-9b"

# Project-specific model overrides
PROJECT_MODELS = {
    "openmind": {
        "vision": DEFAULT_VISION_MODEL,
        "reasoning": DEFAULT_REASONING_MODEL,
        "code": DEFAULT_CODE_MODEL,
    },
    "geometry_os": {
        "vision": DEFAULT_VISION_MODEL,
        "reasoning": "qwen/qwen3-coder-30b",
        "code": "qwen/qwen3-coder-30b",
    },
}

# CTRM scoring weights
CTRM_WEIGHTS = {
    "coherent": 1.0,
    "authentic": 1.0,
    "actionable": 1.0,
    "meaningful": 1.0,
    "grounded": 1.0,
}

# Prioritization weights
PRIORITIZATION_WEIGHTS = {
    "urgency": 5.0,
    "quality": 3.0,
    "impact": 1.5,
    "fresh_bonus": 2.0,
    "stale_penalty": -1.0,
}
