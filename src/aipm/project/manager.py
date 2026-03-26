"""
Project Manager - Manage projects and tasks

Provides project organization with tasks, dependencies, and milestones.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import uuid


class TaskStatus(str, Enum):
    """Status of a task"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Priority of a task"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Task:
    """A task in a project"""
    id: str
    project_id: str
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: List[str] = field(default_factory=list)  # Task IDs
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    assignee: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    milestone_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "assignee": self.assignee,
            "tags": self.tags,
            "metadata": self.metadata,
            "milestone_id": self.milestone_id,
        }


@dataclass
class Milestone:
    """A milestone in a project"""
    id: str
    project_id: str
    name: str
    description: str = ""
    due_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Project:
    """A project being managed"""
    id: str
    name: str
    goal: str
    path: Optional[Path] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "path": str(self.path) if self.path else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "build_command": self.build_command,
            "test_command": self.test_command,
            "metadata": self.metadata,
        }


class ProjectManager:
    """
    Manages projects, tasks, milestones, and dependencies.
    
    Integrates with:
    - PromptSystem for generating prompts from tasks
    - ASCII World for dashboard updates
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".aipm" / "data" / "projects.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema"""
        with sqlite3.connect(self.db_path) as conn:
            # Projects table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    build_command TEXT,
                    test_command TEXT,
                    metadata TEXT
                )
            """)
            
            # Milestones table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS milestones (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    due_date TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)
            
            # Tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'medium',
                    dependencies TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    assignee TEXT,
                    tags TEXT,
                    metadata TEXT,
                    milestone_id TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (milestone_id) REFERENCES milestones(id)
                )
            """)
            
            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id)
            """)
    
    # === Project Operations ===
    
    def create_project(
        self,
        name: str,
        goal: str,
        path: Optional[Path] = None,
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
    ) -> Project:
        """Create a new project"""
        project = Project(
            id=f"proj_{uuid.uuid4().hex[:8]}",
            name=name,
            goal=goal,
            path=path,
            build_command=build_command,
            test_command=test_command,
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO projects (
                    id, name, goal, path, created_at, updated_at,
                    build_command, test_command, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project.id,
                project.name,
                project.goal,
                str(project.path) if project.path else None,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
                project.build_command,
                project.test_command,
                json.dumps(project.metadata),
            ))
        
        self._update_ascii_dashboard()
        return project
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_project(row)
        return None
    
    def list_projects(self) -> List[Project]:
        """List all projects"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            )
            return [self._row_to_project(row) for row in cursor.fetchall()]
    
    def update_project(self, project: Project) -> None:
        """Update a project"""
        project.updated_at = datetime.now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE projects SET
                    name = ?, goal = ?, path = ?, updated_at = ?,
                    build_command = ?, test_command = ?, metadata = ?
                WHERE id = ?
            """, (
                project.name,
                project.goal,
                str(project.path) if project.path else None,
                project.updated_at.isoformat(),
                project.build_command,
                project.test_command,
                json.dumps(project.metadata),
                project.id,
            ))
        self._update_ascii_dashboard()
    
    def delete_project(self, project_id: str) -> None:
        """Delete a project and all its tasks"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM milestones WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._update_ascii_dashboard()
    
    # === Task Operations ===
    
    def add_task(
        self,
        project_id: str,
        name: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None,
        milestone_id: Optional[str] = None,
    ) -> Task:
        """Add a task to a project"""
        task = Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            name=name,
            description=description,
            priority=priority,
            dependencies=dependencies or [],
            milestone_id=milestone_id,
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO tasks (
                    id, project_id, name, description, status, priority,
                    dependencies, created_at, updated_at, completed_at,
                    assignee, tags, metadata, milestone_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.project_id,
                task.name,
                task.description,
                task.status.value,
                task.priority.value,
                json.dumps(task.dependencies),
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
                task.completed_at.isoformat() if task.completed_at else None,
                task.assignee,
                json.dumps(task.tags),
                json.dumps(task.metadata),
                task.milestone_id,
            ))
        
        self._update_ascii_dashboard()
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_task(row)
        return None
    
    def get_project_tasks(self, project_id: str) -> List[Task]:
        """Get all tasks for a project"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at",
                (project_id,)
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]
    
    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Update a task's status"""
        now = datetime.now()
        completed_at = now if status == TaskStatus.COMPLETED else None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE tasks SET status = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
            """, (status.value, now.isoformat(), 
                  completed_at.isoformat() if completed_at else None, task_id))
        
        self._update_ascii_dashboard()
    
    def get_ready_tasks(self, project_id: str) -> List[Task]:
        """Get tasks that are ready to work on (dependencies satisfied)"""
        tasks = self.get_project_tasks(project_id)
        completed_ids = {t.id for t in tasks if t.status == TaskStatus.COMPLETED}
        
        ready = []
        for task in tasks:
            if task.status != TaskStatus.PENDING:
                continue
            # Check if all dependencies are completed
            if all(dep_id in completed_ids for dep_id in task.dependencies):
                ready.append(task)
        
        return ready
    
    # === Milestone Operations ===
    
    def add_milestone(
        self,
        project_id: str,
        name: str,
        description: str = "",
        due_date: Optional[datetime] = None,
    ) -> Milestone:
        """Add a milestone to a project"""
        milestone = Milestone(
            id=f"mile_{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            name=name,
            description=description,
            due_date=due_date,
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO milestones (id, project_id, name, description, due_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                milestone.id,
                milestone.project_id,
                milestone.name,
                milestone.description,
                milestone.due_date.isoformat() if milestone.due_date else None,
                milestone.created_at.isoformat(),
            ))
        
        self._update_ascii_dashboard()
        return milestone
    
    def get_project_milestones(self, project_id: str) -> List[Milestone]:
        """Get all milestones for a project"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM milestones WHERE project_id = ? ORDER BY due_date",
                (project_id,)
            )
            return [self._row_to_milestone(row) for row in cursor.fetchall()]
    
    # === Statistics ===
    
    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """Get statistics for a project"""
        tasks = self.get_project_tasks(project_id)
        
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
        
        return {
            "total_tasks": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "blocked": blocked,
            "completion_percentage": (completed / total * 100) if total > 0 else 0,
        }
    
    def _update_ascii_dashboard(self) -> None:
        """Update the ASCII dashboard with current state"""
        dashboard_path = Path.home() / ".aipm" / "ascii" / "projects_dashboard.ascii"
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        
        projects = self.list_projects()
        
        lines = [
            "╔══════════════════════════════════════════════════════════════════╗",
            "║                    AIPM PROJECT DASHBOARD                        ║",
            "╚══════════════════════════════════════════════════════════════════╝",
            "",
        ]
        
        for project in projects[:10]:  # Show top 10
            stats = self.get_project_stats(project.id)
            completion = stats["completion_percentage"]
            
            # Progress bar
            filled = int(completion / 5)
            bar = "█" * filled + "░" * (20 - filled)
            
            lines.append(f"┌─ {project.name} ({project.id}) ─────────────────────────────┐")
            lines.append(f"│ Goal: {project.goal[:50]:<50} │")
            lines.append(f"│ [{bar}] {completion:5.1f}% │")
            lines.append(f"│ Tasks: {stats['completed']}/{stats['total_tasks']} │ Pending: {stats['pending']:<3} │")
            lines.append("└──────────────────────────────────────────────────────────────┘")
            lines.append("")
        
        if not projects:
            lines.append("No projects yet. Create one with: aipm project create")
        
        dashboard_path.write_text("\n".join(lines))
    
    # === Row Converters ===
    
    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            goal=row["goal"],
            path=Path(row["path"]) if row["path"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            build_command=row["build_command"],
            test_command=row["test_command"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"] or "",
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            dependencies=json.loads(row["dependencies"]) if row["dependencies"] else [],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            assignee=row["assignee"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            milestone_id=row["milestone_id"],
        )
    
    def _row_to_milestone(self, row: sqlite3.Row) -> Milestone:
        return Milestone(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"] or "",
            due_date=datetime.fromisoformat(row["due_date"]) if row["due_date"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
