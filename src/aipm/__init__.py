"""
AIPM - AI Project Manager

The foundation for AI-driven development. Provides:
- Prompt management with intelligent prioritization
- CTRM (Contextual Truth Reference Model) for knowledge storage
- ASCII World for visual dashboards
- Project management with task dependencies
- REST + WebSocket API for integration

Usage:
    from aipm import AIPM
    
    # Initialize the system
    aipm = AIPM()
    
    # Create a project
    project = aipm.create_project(
        name="My App",
        goal="Build something amazing",
    )
    
    # Add a prompt
    prompt_id = aipm.enqueue("Write code for feature X")
    
    # Process prompts
    result = await aipm.process_next()
"""

__version__ = "0.1.0"
__author__ = "Jericho"

# Configuration
from aipm.config import (
    DATA_DIR,
    CTRM_DB,
    QUEUE_DB,
    PROJECTS_DB,
    DEFAULT_PROVIDER,
)

# Core components (simple versions)
from aipm.core.engine import PromptEngine, Prompt, PromptCategory
from aipm.core.queue import PromptQueue
from aipm.core.analyzer import ResponseAnalyzer
from aipm.core.prioritizer import PromptPrioritizer

# Enhanced components (from ouroboros)
try:
    from aipm.core.ctrm_prompt_manager import CTRMPromptManager
    from aipm.core.unified_prompt_engine import UnifiedPromptEngine
    from aipm.core.queue_bridge import QueueBridge
    from aipm.core.automated_loop import AutomatedPromptLoop
    ENHANCED_AVAILABLE = True
except ImportError:
    ENHANCED_AVAILABLE = False

# CTRM
from aipm.ctrm.database import CTRMDatabase, Truth

# Project management
from aipm.project.manager import ProjectManager, Project, Task

# ASCII World
from aipm.ascii_world.dashboard import Dashboard

# Integration
from aipm.integration import AIPM, get_aipm

__all__ = [
    # Main entry point
    "AIPM",
    "get_aipm",
    
    # Configuration
    "DATA_DIR",
    "CTRM_DB",
    "QUEUE_DB",
    "PROJECTS_DB",
    "DEFAULT_PROVIDER",
    
    # Core (simple)
    "PromptEngine",
    "Prompt",
    "PromptCategory",
    "PromptQueue",
    "ResponseAnalyzer",
    "PromptPrioritizer",
    
    # Core (enhanced)
    "CTRMPromptManager",
    "UnifiedPromptEngine",
    "QueueBridge",
    "AutomatedPromptLoop",
    
    # CTRM
    "CTRMDatabase",
    "Truth",
    
    # Project management
    "ProjectManager",
    "Project",
    "Task",
    
    # ASCII World
    "Dashboard",
    
    # Status
    "ENHANCED_AVAILABLE",
]
