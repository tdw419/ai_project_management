"""
AIPM - AI Project Manager

The foundation for AI-driven development. Provides:
- Prompt management with intelligent prioritization
- CTRM (Contextual Truth Reference Model) for knowledge storage
- ASCII World for visual dashboards
- Project management with task dependencies
- REST + WebSocket API for integration

Usage:
    from aipm import PromptSystem, ProjectManager, Dashboard
    
    # Initialize the system
    system = PromptSystem()
    pm = ProjectManager()
    dashboard = Dashboard()
    
    # Create a project
    project = pm.create_project(
        name="My App",
        goal="Build something amazing",
        path="/path/to/project"
    )
    
    # Process prompts
    result = system.process_next()
"""

__version__ = "0.1.0"
__author__ = "Jericho"

from aipm.core.engine import PromptEngine, PromptSystem
from aipm.core.queue import PromptQueue
from aipm.core.analyzer import ResponseAnalyzer
from aipm.core.prioritizer import PromptPrioritizer
from aipm.ctrm.database import CTRMDatabase
from aipm.project.manager import ProjectManager
from aipm.ascii_world.dashboard import Dashboard

__all__ = [
    "PromptEngine",
    "PromptSystem",
    "PromptQueue",
    "ResponseAnalyzer",
    "PromptPrioritizer",
    "CTRMDatabase",
    "ProjectManager",
    "Dashboard",
]
