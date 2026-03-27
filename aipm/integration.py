"""
AIPM Integration - Brings all components together

This is the main entry point for using AIPM in your projects.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

# Use config for paths
from aipm.config import CTRM_DB, QUEUE_DB, PROJECTS_DB, DATA_DIR


class AIPM:
    """
    The unified AIPM system.
    
    Usage:
        from aipm.integration import AIPM
        
        # Initialize
        aipm = AIPM()
        
        # Or with custom paths
        aipm = AIPM(
            ctrm_db="/path/to/truths.db",
            queue_db="/path/to/queue.db",
        )
        
        # Create a project
        project = aipm.create_project(
            name="My Project",
            goal="Build something amazing",
        )
        
        # Add a task
        task = aipm.add_task(
            project_id=project.id,
            name="Implement feature X",
        )
        
        # Add a prompt
        prompt_id = aipm.enqueue("Write code for feature X")
        
        # Process the next prompt
        result = await aipm.process_next()
        
        # Get status
        stats = aipm.get_stats()
    """
    
    def __init__(
        self,
        data_dir: Optional[Path] = None,
        ctrm_db: Optional[Path] = None,
        queue_db: Optional[Path] = None,
        projects_db: Optional[Path] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Database paths - use config defaults
        self.ctrm_db = Path(ctrm_db) if ctrm_db else CTRM_DB
        self.queue_db = Path(queue_db) if queue_db else QUEUE_DB
        self.projects_db = Path(projects_db) if projects_db else PROJECTS_DB
        
        # Initialize components (lazy loading)
        self._ctrm_manager = None
        self._project_manager = None
        self._queue_bridge = None
        self._prompt_engine = None
    
    @property
    def ctrm(self):
        """Get CTRM manager"""
        if self._ctrm_manager is None:
            from aipm.core.ctrm_prompt_manager import CTRMPromptManager
            self._ctrm_manager = CTRMPromptManager(db_path=self.ctrm_db)
        return self._ctrm_manager
    
    @property
    def projects(self):
        """Get project manager"""
        if self._project_manager is None:
            # Use our simpler project manager from backup
            import sys
            backup_path = Path(__file__).parent.parent.parent / "backup"
            if backup_path.exists():
                sys.path.insert(0, str(backup_path))
            from aipm.project.manager import ProjectManager
            self._project_manager = ProjectManager(db_path=self.projects_db)
        return self._project_manager
    
    @property
    def bridge(self):
        """Get queue bridge (simple, synchronous version)"""
        if self._queue_bridge is None:
            from aipm.core.simple_bridge import SyncQueueBridge
            self._queue_bridge = SyncQueueBridge()
        return self._queue_bridge
    
    @property
    def bridge_async(self):
        """Get async queue bridge"""
        if self._queue_bridge_async is None:
            try:
                from aipm.core.queue_bridge import PromptQueueBridge
                self._queue_bridge_async = PromptQueueBridge()
            except ImportError:
                self._queue_bridge_async = None
        return self._queue_bridge_async
    
    # === Project Management ===
    
    def create_project(
        self,
        name: str,
        goal: str,
        path: Optional[Path] = None,
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
    ):
        """Create a new project"""
        return self.projects.create_project(
            name=name,
            goal=goal,
            path=path,
            build_command=build_command,
            test_command=test_command,
        )
    
    def add_task(
        self,
        project_id: str,
        name: str,
        description: str = "",
        priority: str = "medium",
        dependencies: Optional[List[str]] = None,
    ):
        """Add a task to a project"""
        from aipm.project.manager import TaskPriority
        return self.projects.add_task(
            project_id=project_id,
            name=name,
            description=description,
            priority=TaskPriority(priority),
            dependencies=dependencies,
        )
    
    def get_project(self, project_id: str):
        """Get a project by ID"""
        return self.projects.get_project(project_id)
    
    def list_projects(self):
        """List all projects"""
        return self.projects.list_projects()
    
    # === Prompt Management ===
    
    def enqueue(
        self,
        prompt: str,
        priority: int = 5,
        source: str = "manual",
        metadata: Optional[Dict] = None,
    ) -> str:
        """Add a prompt to the queue"""
        return self.ctrm.enqueue(
            prompt=prompt,
            priority=priority,
            source=source,
            metadata=metadata,
        )
    
    def dequeue(self, limit: int = 1) -> List[Dict]:
        """Get the next prompt(s) from the queue"""
        return self.ctrm.dequeue(limit=limit)
    
    async def process_next(self, provider: Optional[str] = None) -> Optional[Dict]:
        """Process the next prompt"""
        return await self.ctrm.process_next(provider_preference=provider)
    
    # === Statistics ===
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        ctrm_stats = self.ctrm.get_stats()
        
        try:
            projects = self.projects.list_projects()
            project_count = len(projects)
        except:
            project_count = 0
        
        return {
            "queue": ctrm_stats,
            "projects": project_count,
            "data_dir": str(self.data_dir),
        }
    
    # === Automation ===
    
    async def run_loop(
        self,
        interval: int = 60,
        max_iterations: Optional[int] = None,
    ):
        """Run the processing loop"""
        iteration = 0
        while max_iterations is None or iteration < max_iterations:
            result = await self.process_next()
            if result:
                print(f"[{iteration}] Processed: {result['prompt_id']}")
            else:
                print(f"[{iteration}] No pending prompts")
            
            iteration += 1
            await asyncio.sleep(interval)
    
    # === ASCII World ===
    
    def get_dashboard(self) -> str:
        """Get ASCII dashboard"""
        dashboard_path = Path(__file__).parent.parent.parent / "ascii_world" / "control_center.ascii"
        if dashboard_path.exists():
            return dashboard_path.read_text()
        return "Dashboard not found"
    
    def get_control_center_html(self) -> str:
        """Get HTML control center"""
        html_path = Path(__file__).parent.parent.parent / "ascii_world" / "control_center.html"
        if html_path.exists():
            return html_path.read_text()
        return "<html><body>Control Center not found</body></html>"


# Convenience function
def get_aipm(**kwargs) -> AIPM:
    """Get an AIPM instance"""
    return AIPM(**kwargs)
