"""
AIPM Project Models

Data models for projects, tasks, and milestones.
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ProjectStatus(Enum):
    """Project status enumeration."""
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass
class Task:
    """A single task within a project."""
    id: str
    project_id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    dependencies: List[str] = field(default_factory=list)
    prompt_id: Optional[str] = None
    result: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            **asdict(self),
            'status': self.status.value
        }


@dataclass
class Milestone:
    """A milestone grouping tasks."""
    id: str
    project_id: str
    name: str
    description: str
    tasks: List[str] = field(default_factory=list)
    target_date: Optional[str] = None
    
    def completion_percentage(self, all_tasks: Dict[str, Task]) -> float:
        """Calculate completion percentage."""
        if not self.tasks:
            return 0.0
        completed = sum(1 for tid in self.tasks 
                       if tid in all_tasks and all_tasks[tid].status == TaskStatus.COMPLETED)
        return (completed / len(self.tasks)) * 100


@dataclass
class Project:
    """A project with goals, milestones, and tasks."""
    id: str
    name: str
    description: str
    goal: str
    status: ProjectStatus = ProjectStatus.PLANNING
    root_path: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    milestones: List[Milestone] = field(default_factory=list)
    tasks: Dict[str, Task] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def completion_percentage(self) -> float:
        """Calculate overall completion percentage."""
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        return (completed / len(self.tasks)) * 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            **asdict(self),
            'status': self.status.value,
            'tasks': {tid: t.to_dict() for tid, t in self.tasks.items()},
            'milestones': [asdict(m) for m in self.milestones]
        }


__all__ = [
    "TaskStatus",
    "ProjectStatus",
    "Task",
    "Milestone",
    "Project",
]
