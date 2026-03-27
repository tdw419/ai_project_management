#!/usr/bin/env python3
"""
Ouroboros Project Manager

Manages projects as structured collections of tasks that integrate
with the CTRM prompt queue.

Features:
- Define projects with goals, milestones, and tasks
- Auto-generate prompts from project tasks
- Track project completion percentage
- Manage task dependencies
- Build/test integration
- Project status in ASCII dashboard
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

from aipm.config import CTRM_DB, PROJECTS_DB


class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ProjectStatus(Enum):
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
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks.values() 
                       if t.status == TaskStatus.COMPLETED)
        return (completed / len(self.tasks)) * 100
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'goal': self.goal,
            'status': self.status.value,
            'root_path': self.root_path,
            'completion': self.completion_percentage(),
            'task_count': len(self.tasks),
            'milestone_count': len(self.milestones),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class ProjectManager:
    """
    Manages projects and integrates with CTRM prompt queue.
    """
    
    def __init__(self, db_path: Path = PROJECTS_DB):
        self.db_path = db_path
        self.projects: Dict[str, Project] = {}
        self._init_db()
        self._load_projects()
    
    def _init_db(self):
        """Initialize the projects database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Projects table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                goal TEXT,
                status TEXT DEFAULT 'planning',
                root_path TEXT,
                build_command TEXT,
                test_command TEXT,
                config_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                dependencies_json TEXT,
                prompt_id TEXT,
                result TEXT,
                created_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        
        # Milestones table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                tasks_json TEXT,
                target_date TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _load_projects(self):
        """Load all projects from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Load projects
        cursor.execute("SELECT * FROM projects")
        for row in cursor.fetchall():
            project_id = row[0]
            
            # Load tasks for this project
            cursor.execute("SELECT * FROM tasks WHERE project_id = ?", (project_id,))
            tasks = {}
            for trow in cursor.fetchall():
                task = Task(
                    id=trow[0],
                    project_id=trow[1],
                    name=trow[2],
                    description=trow[3],
                    status=TaskStatus(trow[4]),
                    priority=trow[5],
                    dependencies=json.loads(trow[6] or '[]'),
                    prompt_id=trow[7],
                    result=trow[8],
                    created_at=trow[9],
                    completed_at=trow[10]
                )
                tasks[task.id] = task
            
            # Load milestones
            cursor.execute("SELECT * FROM milestones WHERE project_id = ?", (project_id,))
            milestones = []
            for mrow in cursor.fetchall():
                milestone = Milestone(
                    id=mrow[0],
                    project_id=mrow[1],
                    name=mrow[2],
                    description=mrow[3],
                    tasks=json.loads(mrow[4] or '[]'),
                    target_date=mrow[5]
                )
                milestones.append(milestone)
            
            project = Project(
                id=row[0],
                name=row[1],
                description=row[2],
                goal=row[3],
                status=ProjectStatus(row[4]),
                root_path=row[5],
                build_command=row[6],
                test_command=row[7],
                milestones=milestones,
                tasks=tasks,
                created_at=row[9],
                updated_at=row[10]
            )
            self.projects[project_id] = project
        
        conn.close()
    
    def _save_project(self, project: Project):
        """Save a project to database and update ASCII dashboard."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Save project
        cursor.execute("""
            INSERT OR REPLACE INTO projects 
            (id, name, description, goal, status, root_path, build_command, test_command, 
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project.id, project.name, project.description, project.goal,
              project.status.value, project.root_path, project.build_command,
              project.test_command, project.created_at, project.updated_at))
        
        # Save tasks
        for task in project.tasks.values():
            cursor.execute("""
                INSERT OR REPLACE INTO tasks
                (id, project_id, name, description, status, priority, dependencies_json,
                 prompt_id, result, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (task.id, task.project_id, task.name, task.description,
                  task.status.value, task.priority, json.dumps(task.dependencies),
                  task.prompt_id, task.result, task.created_at, task.completed_at))
        
        # Save milestones
        for milestone in project.milestones:
            cursor.execute("""
                INSERT OR REPLACE INTO milestones
                (id, project_id, name, description, tasks_json, target_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (milestone.id, milestone.project_id, milestone.name,
                  milestone.description, json.dumps(milestone.tasks), milestone.target_date))
        
        conn.commit()
        conn.close()
        
        # MANDATORY: Update ASCII dashboard
        self._update_ascii_dashboard()
    
    def _update_ascii_dashboard(self):
        """Update the ASCII dashboard file with current project state."""
        import hashlib
        from pathlib import Path
        
        ascii_path = from aipm.config import .OUROBOROS; .OUROBOROS / "project_dashboard.ascii"
        ascii_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Count by status
        active = sum(1 for p in self.projects.values() if p.status == ProjectStatus.ACTIVE)
        completed = sum(1 for p in self.projects.values() if p.status == ProjectStatus.COMPLETED)
        planning = sum(1 for p in self.projects.values() if p.status == ProjectStatus.PLANNING)
        paused = sum(1 for p in self.projects.values() if p.status == ProjectStatus.PAUSED)
        
        # Build ASCII content
        content = f"""# Ouroboros Project Dashboard

ver:pending

┌──────────────────────────────────────────────────────────────────────────┐
│  🏗️ OUROBOROS PROJECT MANAGER                                            │
├──────────────────────────────────────────────────────────────────────────┤
│  Active: {active}    Completed: {completed}    Planning: {planning}    Paused: {paused}                   │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  ACTIVE PROJECTS                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
"""
        
        # Add each active project
        for project in self.list_projects(status=ProjectStatus.ACTIVE):
            completion = project.completion_percentage()
            task_count = len(project.tasks)
            completed_tasks = sum(1 for t in project.tasks.values() if t.status == TaskStatus.COMPLETED)
            
            content += f"""  ┌─────────────────────────────────────────────────────────────────────┐
  │ {project.name[:60]:<60} │
  │ Status: {project.status.value:<10} Completion: {completion:>5.0f}%    Tasks: {completed_tasks}/{task_count}                   │
  ├─────────────────────────────────────────────────────────────────────┤
  │ Goal: {project.goal[:60]:<60} │
  │ Path: {project.root_path or 'N/A':<60} │
  │                                                                     │
"""
            
            # Add milestones if any
            if project.milestones:
                content += "  │ Milestones:                                                         │\n"
                for ms in project.milestones[:3]:
                    ms_pct = ms.completion_percentage(project.tasks)
                    icon = "✓" if ms_pct == 100 else ("◐" if ms_pct > 0 else "○")
                    content += f"  │   {icon} {ms.name[:50]:<50} ({ms_pct:>5.0f}%)      │\n"
            
            # Add recent tasks
            content += "  │                                                                     │\n"
            content += "  │ Recent Tasks:                                                      │\n"
            
            tasks_by_status = sorted(
                project.tasks.values(),
                key=lambda t: (t.status.value, t.priority)
            )[:5]
            
            for task in tasks_by_status:
                icon = {
                    TaskStatus.COMPLETED: "✓",
                    TaskStatus.IN_PROGRESS: "●",
                    TaskStatus.QUEUED: "◐",
                    TaskStatus.PENDING: "○",
                    TaskStatus.FAILED: "✗",
                    TaskStatus.BLOCKED: "⊘"
                }.get(task.status, "?")
                
                content += f"  │   {icon} {task.name[:55]:<55}   │\n"
            
            content += "  │                                                                     │\n"
            content += "  │ [V] View Details  [B] Build  [T] Test  [Q] Queue Ready Tasks       │\n"
            content += "  └─────────────────────────────────────────────────────────────────────┘\n"
            content += "│                                                                           │\n"
        
        content += """├──────────────────────────────────────────────────────────────────────────┤
│  [N] New Project    [R] Refresh    [F] Filter    [S] Stats               │
└──────────────────────────────────────────────────────────────────────────┘
"""
        
        # Compute hash
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        content = content.replace("ver:pending", f"ver:{content_hash}")
        
        # Write file
        with open(ascii_path, "w") as f:
            f.write(content)
        
        return content_hash
    
    # === Project Operations ===
    
    def create_project(self, name: str, goal: str, description: str = "",
                       root_path: Optional[str] = None,
                       build_command: Optional[str] = None,
                       test_command: Optional[str] = None) -> Project:
        """Create a new project."""
        project_id = f"proj_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        
        project = Project(
            id=project_id,
            name=name,
            description=description,
            goal=goal,
            root_path=root_path,
            build_command=build_command,
            test_command=test_command
        )
        
        self.projects[project_id] = project
        self._save_project(project)
        
        return project
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        return self.projects.get(project_id)
    
    def list_projects(self, status: Optional[ProjectStatus] = None) -> List[Project]:
        """List all projects, optionally filtered by status."""
        projects = list(self.projects.values())
        if status:
            projects = [p for p in projects if p.status == status]
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)
    
    def update_project_status(self, project_id: str, status: ProjectStatus):
        """Update project status."""
        project = self.projects.get(project_id)
        if project:
            project.status = status
            project.updated_at = datetime.now().isoformat()
            self._save_project(project)
    
    # === Task Operations ===
    
    def add_task(self, project_id: str, name: str, description: str,
                 priority: int = 5, dependencies: List[str] = None) -> Task:
        """Add a task to a project."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        task_id = f"task_{hashlib.md5(f'{project_id}_{name}'.encode()).hexdigest()[:8]}"
        
        task = Task(
            id=task_id,
            project_id=project_id,
            name=name,
            description=description,
            priority=priority,
            dependencies=dependencies or []
        )
        
        project.tasks[task_id] = task
        project.updated_at = datetime.now().isoformat()
        self._save_project(project)
        
        return task
    
    def update_task_status(self, project_id: str, task_id: str, status: TaskStatus,
                           result: Optional[str] = None):
        """Update task status."""
        project = self.projects.get(project_id)
        if not project or task_id not in project.tasks:
            return
        
        task = project.tasks[task_id]
        task.status = status
        
        if result:
            task.result = result
        
        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now().isoformat()
        
        project.updated_at = datetime.now().isoformat()
        self._save_project(project)
    
    def get_ready_tasks(self, project_id: str) -> List[Task]:
        """Get tasks that are ready to be queued (dependencies met)."""
        project = self.projects.get(project_id)
        if not project:
            return []
        
        ready = []
        for task in project.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            
            # Check dependencies
            deps_met = all(
                project.tasks.get(dep_id, Task(id="", project_id="", name="", description="")).status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
            )
            
            if deps_met:
                ready.append(task)
        
        return sorted(ready, key=lambda t: t.priority)
    
    # === Milestone Operations ===
    
    def add_milestone(self, project_id: str, name: str, description: str,
                      task_ids: List[str] = None, target_date: str = None) -> Milestone:
        """Add a milestone to a project."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        milestone_id = f"ms_{hashlib.md5(f'{project_id}_{name}'.encode()).hexdigest()[:8]}"
        
        milestone = Milestone(
            id=milestone_id,
            project_id=project_id,
            name=name,
            description=description,
            tasks=task_ids or [],
            target_date=target_date
        )
        
        project.milestones.append(milestone)
        project.updated_at = datetime.now().isoformat()
        self._save_project(project)
        
        return milestone
    
    # === Queue Integration ===
    
    def queue_task(self, project_id: str, task_id: str) -> str:
        """Queue a task as a prompt in CTRM."""
        project = self.projects.get(project_id)
        if not project or task_id not in project.tasks:
            raise ValueError(f"Task not found: {task_id}")
        
        task = project.tasks[task_id]
        
        # Generate prompt text from task
        prompt_text = self._generate_prompt_from_task(project, task)
        
        # Add to CTRM queue
        try:
            from ouroboros.core.ctrm_prompt_manager import CTRMPromptManager
            manager = CTRMPromptManager()
            
            prompt_id = manager.enqueue(
                prompt=prompt_text,
                priority=task.priority,
                source=f"project:{project_id}:{task_id}"
            )
        except ImportError:
            # Fallback if CTRM manager not available
            prompt_id = f"prompt_{hashlib.md5(prompt_text.encode()).hexdigest()[:8]}"
            print(f"Warning: CTRM manager not available, using generated ID: {prompt_id}")
        
        # Update task with prompt_id
        task.prompt_id = prompt_id
        task.status = TaskStatus.QUEUED
        project.updated_at = datetime.now().isoformat()
        self._save_project(project)
        
        return prompt_id
    
    def queue_all_ready_tasks(self, project_id: str) -> List[str]:
        """Queue all ready tasks for a project."""
        ready = self.get_ready_tasks(project_id)
        prompt_ids = []
        
        for task in ready:
            try:
                prompt_id = self.queue_task(project_id, task.id)
                prompt_ids.append(prompt_id)
            except Exception as e:
                print(f"Failed to queue task {task.id}: {e}")
        
        return prompt_ids
    
    def _generate_prompt_from_task(self, project: Project, task: Task) -> str:
        """Generate a prompt text from a task."""
        parts = [
            f"Project: {project.name}",
            f"Goal: {project.goal}",
            f"",
            f"Task: {task.name}",
            f"Description: {task.description}",
            f""
        ]
        
        if project.root_path:
            parts.append(f"Working Directory: {project.root_path}")
        
        if task.dependencies:
            parts.append(f"Dependencies: {', '.join(task.dependencies)}")
        
        parts.append(f"")
        parts.append(f"Complete this task and report the results.")
        
        return "\n".join(parts)
    
    # === Build/Test Integration ===
    
    def run_build(self, project_id: str) -> Dict:
        """Run the build command for a project."""
        project = self.projects.get(project_id)
        if not project or not project.build_command:
            return {'success': False, 'error': 'No build command configured'}
        
        import subprocess
        
        try:
            result = subprocess.run(
                project.build_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=project.root_path,
                timeout=300
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def run_tests(self, project_id: str) -> Dict:
        """Run the test command for a project."""
        project = self.projects.get(project_id)
        if not project or not project.test_command:
            return {'success': False, 'error': 'No test command configured'}
        
        import subprocess
        
        try:
            result = subprocess.run(
                project.test_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=project.root_path,
                timeout=300
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # === Statistics ===
    
    def get_project_stats(self, project_id: str) -> Dict:
        """Get statistics for a project."""
        project = self.projects.get(project_id)
        if not project:
            return {}
        
        tasks = list(project.tasks.values())
        
        return {
            'total_tasks': len(tasks),
            'completed': sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            'in_progress': sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS),
            'queued': sum(1 for t in tasks if t.status == TaskStatus.QUEUED),
            'pending': sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            'failed': sum(1 for t in tasks if t.status == TaskStatus.FAILED),
            'blocked': sum(1 for t in tasks if t.status == TaskStatus.BLOCKED),
            'completion_percentage': project.completion_percentage(),
            'milestones': len(project.milestones)
        }
    
    def get_all_stats(self) -> Dict:
        """Get statistics for all projects."""
        all_projects = list(self.projects.values())
        
        return {
            'total_projects': len(all_projects),
            'active': sum(1 for p in all_projects if p.status == ProjectStatus.ACTIVE),
            'completed': sum(1 for p in all_projects if p.status == ProjectStatus.COMPLETED),
            'paused': sum(1 for p in all_projects if p.status == ProjectStatus.PAUSED),
            'planning': sum(1 for p in all_projects if p.status == ProjectStatus.PLANNING)
        }


# === CLI ===

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Ouroboros Project Manager")
    parser.add_argument("command", choices=[
        "create", "list", "show", "add-task", "queue", "build", "test", "stats"
    ])
    parser.add_argument("--name", help="Project name")
    parser.add_argument("--goal", help="Project goal")
    parser.add_argument("--path", help="Root path")
    parser.add_argument("--project-id", help="Project ID")
    parser.add_argument("--task-name", help="Task name")
    parser.add_argument("--task-desc", help="Task description")
    parser.add_argument("--priority", type=int, default=5)
    
    args = parser.parse_args()
    
    manager = ProjectManager()
    
    if args.command == "create":
        if not args.name or not args.goal:
            print("Error: --name and --goal required")
            return
        
        project = manager.create_project(
            name=args.name,
            goal=args.goal,
            root_path=args.path
        )
        print(f"Created project: {project.id}")
        print(f"  Name: {project.name}")
        print(f"  Goal: {project.goal}")
    
    elif args.command == "list":
        projects = manager.list_projects()
        print(f"\n{'='*70}")
        print(f"PROJECTS ({len(projects)} total)")
        print(f"{'='*70}\n")
        
        for p in projects:
            completion = p.completion_percentage()
            print(f"  [{p.status.value:8}] {p.name}")
            print(f"    ID: {p.id}")
            print(f"    Completion: {completion:.1f}% ({len([t for t in p.tasks.values() if t.status == TaskStatus.COMPLETED])}/{len(p.tasks)} tasks)")
            print()
    
    elif args.command == "show":
        if not args.project_id:
            print("Error: --project-id required")
            return
        
        project = manager.get_project(args.project_id)
        if not project:
            print(f"Project not found: {args.project_id}")
            return
        
        print(f"\n{'='*70}")
        print(f"PROJECT: {project.name}")
        print(f"{'='*70}")
        print(f"ID: {project.id}")
        print(f"Status: {project.status.value}")
        print(f"Goal: {project.goal}")
        print(f"Path: {project.root_path or 'Not set'}")
        print(f"Completion: {project.completion_percentage():.1f}%")
        print(f"\nTASKS ({len(project.tasks)}):")
        
        for task in project.tasks.values():
            icon = {
                TaskStatus.PENDING: "○",
                TaskStatus.QUEUED: "◐",
                TaskStatus.IN_PROGRESS: "●",
                TaskStatus.COMPLETED: "✓",
                TaskStatus.FAILED: "✗",
                TaskStatus.BLOCKED: "⊘"
            }.get(task.status, "?")
            
            print(f"  {icon} [{task.priority}] {task.name}")
        
        if project.milestones:
            print(f"\nMILESTONES ({len(project.milestones)}):")
            for ms in project.milestones:
                pct = ms.completion_percentage(project.tasks)
                print(f"  • {ms.name}: {pct:.0f}%")
    
    elif args.command == "add-task":
        if not args.project_id or not args.task_name:
            print("Error: --project-id and --task-name required")
            return
        
        task = manager.add_task(
            project_id=args.project_id,
            name=args.task_name,
            description=args.task_desc or "",
            priority=args.priority
        )
        print(f"Added task: {task.id}")
    
    elif args.command == "queue":
        if not args.project_id:
            print("Error: --project-id required")
            return
        
        prompt_ids = manager.queue_all_ready_tasks(args.project_id)
        print(f"Queued {len(prompt_ids)} tasks")
        for pid in prompt_ids:
            print(f"  {pid}")
    
    elif args.command == "build":
        if not args.project_id:
            print("Error: --project-id required")
            return
        
        result = manager.run_build(args.project_id)
        print(f"Build: {'✓ SUCCESS' if result['success'] else '✗ FAILED'}")
        if result.get('stdout'):
            print(result['stdout'])
        if result.get('stderr'):
            print(result['stderr'])
    
    elif args.command == "test":
        if not args.project_id:
            print("Error: --project-id required")
            return
        
        result = manager.run_tests(args.project_id)
        print(f"Tests: {'✓ PASSED' if result['success'] else '✗ FAILED'}")
        if result.get('stdout'):
            print(result['stdout'])
        if result.get('stderr'):
            print(result['stderr'])
    
    elif args.command == "stats":
        stats = manager.get_all_stats()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
