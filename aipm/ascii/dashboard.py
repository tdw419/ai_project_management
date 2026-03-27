"""
AIPM ASCII World - Visual Shell and Dashboard

ASCII-based visualization for human oversight of AI operations.
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class Dashboard:
    """
    ASCII Dashboard Generator.
    
    Creates and maintains ASCII state files that are rendered
    by HTML for human oversight.
    """
    
    def __init__(self, workspace: Optional[Path] = None):
        self.workspace = workspace or Path.home() / ".openclaw" / "workspace"
        self.dashboard_dir = self.workspace / ".aipm"
        self.dashboard_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_project_dashboard(
        self,
        projects: Dict[str, Any],
        active_count: int = 0,
        completed_count: int = 0,
        planning_count: int = 0,
        paused_count: int = 0
    ) -> str:
        """Generate ASCII dashboard for projects."""
        
        content = f"""# AIPM Project Dashboard

ver:pending

┌──────────────────────────────────────────────────────────────────────────┐
│  🏗️ AIPM - AI PROJECT MANAGER                                            │
├──────────────────────────────────────────────────────────────────────────┤
│  Active: {active_count}    Completed: {completed_count}    Planning: {planning_count}    Paused: {paused_count}                   │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  ACTIVE PROJECTS                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
"""
        
        # Add each project
        for project_id, project in list(projects.items())[:5]:  # Show max 5
            completion = project.get('completion_percentage', 0)
            task_count = len(project.get('tasks', {}))
            status = project.get('status', 'unknown')
            
            content += f"""  ┌─────────────────────────────────────────────────────────────────────┐
  │ {project.get('name', 'Unnamed')[:60]:<60} │
  │ Status: {status:<10} Completion: {completion:>5.0f}%    Tasks: {task_count}                     │
  ├─────────────────────────────────────────────────────────────────────┤
  │ Goal: {project.get('goal', 'No goal defined')[:60]:<60} │
  │ ID: {project_id:<60} │
  │                                                                     │
"""
            
            # Add recent tasks
            tasks = project.get('tasks', {})
            if tasks:
                content += "  │ Recent Tasks:                                                      │\n"
                for task_id, task in list(tasks.items())[:3]:
                    task_status = task.get('status', 'pending')
                    icon = {
                        'completed': '✓',
                        'in_progress': '●',
                        'queued': '◐',
                        'pending': '○',
                        'failed': '✗',
                        'blocked': '⊘'
                    }.get(task_status, '?')
                    content += f"  │   {icon} {task.get('name', 'Unnamed')[:55]:<55}   │\n"
            
            content += "  └─────────────────────────────────────────────────────────────────────┘\n"
            content += "│                                                                           │\n"
        
        content += """├──────────────────────────────────────────────────────────────────────────┤
│  [N] New Project    [R] Refresh    [F] Filter    [S] Stats               │
└──────────────────────────────────────────────────────────────────────────┘
"""
        
        # Compute hash
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        content = content.replace("ver:pending", f"ver:{content_hash}")
        
        return content
    
    def save_project_dashboard(self, content: str) -> Path:
        """Save dashboard to file."""
        path = self.dashboard_dir / "project_dashboard.ascii"
        with open(path, "w") as f:
            f.write(content)
        return path
    
    def generate_prompt_dashboard(
        self,
        queued: int = 0,
        processing: int = 0,
        completed: int = 0,
        failed: int = 0,
        recent_activity: Optional[list] = None
    ) -> str:
        """Generate ASCII dashboard for prompt queue."""
        
        activity_lines = ""
        if recent_activity:
            for event in recent_activity[-5:]:
                icon = event.get('icon', '•')
                text = event.get('text', '')
                activity_lines += f"│   {icon} {text[:55]:<55}   │\n"
        else:
            activity_lines = "│   (no recent activity)                                              │\n"
        
        content = f"""# AIPM Prompt Dashboard

ver:pending

┌──────────────────────────────────────────────────────────────────────────┐
│  📝 AIPM PROMPT QUEUE                                                     │
├──────────────────────────────────────────────────────────────────────────┤
│  Queued: {queued:<6}  Processing: {processing:<6}  Completed: {completed:<6}  Failed: {failed:<6}       │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  RECENT ACTIVITY                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
{activity_lines}│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  [P] Process    [V] View Queue    [A] Analyze    [R] Refresh            │
└──────────────────────────────────────────────────────────────────────────┘
"""
        
        # Compute hash
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        content = content.replace("ver:pending", f"ver:{content_hash}")
        
        return content
    
    def save_prompt_dashboard(self, content: str) -> Path:
        """Save prompt dashboard to file."""
        path = self.dashboard_dir / "prompt_dashboard.ascii"
        with open(path, "w") as f:
            f.write(content)
        return path


__all__ = ["Dashboard"]
