"""
AIPM Configuration
"""

import os
from pathlib import Path

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import yaml

@dataclass
class ProjectConfig:
    name: str
    path: str
    language: str = "unknown"
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    test_parser: str = "regex"
    test_parser_config: Dict[str, Any] = field(default_factory=lambda: {"regex": r"(\d+)/(\d+)"})
    features: List[str] = field(default_factory=list)
    priority: int = 5
    health_threshold: int = 3
    protected_files: List[str] = field(default_factory=list)  # files pi must not touch
    pi_model: Optional[str] = None  # legacy, still used if hermes_model not set
    hermes_model: Optional[str] = None  # model for hermes agent (e.g. anthropic/claude-sonnet-4)
    skills: List[str] = field(default_factory=list)  # hermes skills to load
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> 'ProjectConfig':
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Ensure path is absolute if relative to yaml
        if not data.get('path'):
            data['path'] = str(path.parent.resolve())
        elif data['path'].startswith('.'):
            data['path'] = str((path.parent / data['path']).resolve())
            
        return cls(**data)

    def to_yaml(self, path: Path):
        with open(path, 'w') as f:
            yaml.dump(self.__dict__, f)

# Default paths - PACKAGE_ROOT is 2 levels up from this file (aipm/config.py -> aipm/ -> repo_root/)
PACKAGE_ROOT = Path(__file__).parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
CTRM_DB = DATA_DIR / "truths.db"
QUEUE_DB = DATA_DIR / "queue.db"
PROJECTS_DB = DATA_DIR / "projects.db"
ASCII_WORLD_DIR = PACKAGE_ROOT / "ascii_world"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Provider configuration - Priority: Ollama > ZAI > LM Studio
DEFAULT_PROVIDER = "ollama"  # Primary: Ollama (local, 27b working)
LM_STUDIO_URL = "http://localhost:1234"

# ZAI configuration (secondary - cloud)
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "")
ZAI_MODEL = "glm-5"  # GLM-5 for reasoning

# Ollama configuration (primary - 27b tools, powerful local reasoning)
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.5-tools"  # Custom model with tool support
USE_OLLAMA_FALLBACK = True

# Default models - use local qwen3.5-tools as the standard
DEFAULT_VISION_MODEL = "qwen3.5-27b" # vision is native in 27b
DEFAULT_REASONING_MODEL = "qwen3.5-tools"
DEFAULT_CODE_MODEL = "qwen3.5-tools"
DEFAULT_CHAT_MODEL = "qwen3.5-tools"
DEFAULT_PI_MODEL = "qwen3.5-tools"

# Project-specific model overrides
PROJECT_MODELS = {
    "openmind": {
        "vision": DEFAULT_VISION_MODEL,
        "reasoning": DEFAULT_REASONING_MODEL,
        "code": DEFAULT_CODE_MODEL,
    },
    "geometry_os": {
        "vision": DEFAULT_VISION_MODEL,
        "reasoning": "qwen2.5-coder",
        "code": "qwen2.5-coder",
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
