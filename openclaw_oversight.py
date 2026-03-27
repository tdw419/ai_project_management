#!/usr/bin/env python3
"""
OpenClaw Project Oversight Script

This script provides a unified interface for OpenClaw to oversee
the development of projects using AIPM.

Usage:
    python3 openclaw_oversight.py status [project_name]
    python3 openclaw_oversight.py next
    python3 openclaw_oversight.py process [--model MODEL]
    python3 openclaw_oversight.py focus [project_name]
    python3 openclaw_oversight.py report
"""

import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path

# Add AIPM to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aipm import AIPM, get_aipm
from aipm.core.simple_bridge import SimpleQueueBridge
from aipm.config import DEFAULT_REASONING_MODEL, DEFAULT_VISION_MODEL


class ProjectOversight:
    """OpenClaw's project oversight system"""
    
    def __init__(self):
        self.aipm = get_aipm()
        self.bridge = SimpleQueueBridge()
        self.current_project = None
    
    def status(self, project_name: str = None):
        """Show status of all projects or a specific project"""
        projects = self.aipm.list_projects()
        
        if project_name:
            projects = [p for p in projects if project_name.lower() in p.name.lower()]
        
        if not projects:
            print("No projects found.")
            return
        
        print("=" * 70)
        print("PROJECT STATUS")
        print("=" * 70)
        
        for project in projects:
            stats = self.aipm.projects.get_project_stats(project.id)
            tasks = self.aipm.projects.get_project_tasks(project.id)
            
            completion_bar = self._progress_bar(stats['completion_percentage'])
            
            print(f"\n📦 {project.name} ({project.id})")
            print(f"   Goal: {project.goal}")
            print(f"   Progress: [{completion_bar}] {stats['completion_percentage']:.1f}%")
            print(f"   Tasks: {stats['total_tasks']} total | {stats['pending']} pending | {stats['completed']} done")
            
            if tasks:
                print("   Task List:")
                for t in tasks[:5]:
                    icon = self._task_icon(t.status.value)
                    priority = t.priority.value[:4].upper()
                    print(f"     {icon} [{priority}] {t.name}")
        
        # Queue status
        queue_stats = self.aipm.get_stats()['queue']
        print(f"\n" + "=" * 70)
        print(f"PROMPT QUEUE: {queue_stats.get('pending_count', 0)} pending | {queue_stats.get('completed_count', 0)} completed")
        print("=" * 70)
    
    def focus(self, project_name: str):
        """Set focus on a specific project"""
        projects = self.aipm.list_projects()
        matching = [p for p in projects if project_name.lower() in p.name.lower()]
        
        if not matching:
            print(f"No project found matching: {project_name}")
            return
        
        self.current_project = matching[0]
        print(f"🎯 Focused on: {self.current_project.name}")
        
        # Show project details
        self.status(project_name)
    
    def next_prompt(self):
        """Show the next prompt to process"""
        prompts = self.aipm.ctrm.dequeue(limit=5)
        
        if not prompts:
            print("No pending prompts.")
            return
        
        print("=" * 70)
        print("NEXT PROMPTS TO PROCESS")
        print("=" * 70)
        
        for i, p in enumerate(prompts):
            print(f"\n{i+1}. [{p['priority']}] {p['id']}")
            print(f"   {p['prompt'][:100]}...")
            print(f"   Confidence: {p.get('confidence', 0):.2f}")
    
    async def process_next(self, model: str = None, use_vision: bool = False):
        """Process the next prompt"""
        prompts = self.aipm.ctrm.dequeue(limit=1)
        
        if not prompts:
            print("No pending prompts to process.")
            return
        
        prompt = prompts[0]
        print(f"\n🔄 Processing: {prompt['id']}")
        print(f"   Prompt: {prompt['prompt'][:100]}...")
        
        # Mark as processing
        self.aipm.ctrm.mark_processing(prompt['id'])
        
        # Determine which model to use
        if use_vision:
            model = model or DEFAULT_VISION_MODEL
            print(f"   Model: {model} (vision)")
        else:
            model = model or DEFAULT_REASONING_MODEL
            print(f"   Model: {model} (reasoning)")
        
        # Process with LM Studio
        result = await self.bridge.process_chat(
            messages=[
                {"role": "system", "content": "You are helping build software projects. Provide detailed, actionable responses with code examples when appropriate."},
                {"role": "user", "content": prompt['prompt']},
            ],
            model=model,
            max_tokens=4096,
            temperature=0.7,
        )
        
        if result.success:
            print(f"\n✅ SUCCESS ({result.wait_time_ms}ms)")
            print("-" * 70)
            print(result.content)
            print("-" * 70)
            
            # Mark as completed
            self.aipm.ctrm.complete(
                prompt['id'],
                result=result.content,
                verified=True,
                notes=f"Processed via {model}"
            )
            
            # Update ASCII dashboard
            self._update_dashboard()
            
            return result.content
        else:
            print(f"\n❌ FAILED: {result.error}")
            self.aipm.ctrm.complete(
                prompt['id'],
                result=f"Error: {result.error}",
                verified=False,
            )
            return None
    
    def report(self):
        """Generate a progress report"""
        stats = self.aipm.get_stats()
        
        print("=" * 70)
        print("📊 AIPM PROGRESS REPORT")
        print(f"   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Projects summary
        print(f"\n📁 PROJECTS: {stats['projects']}")
        
        # Queue summary
        queue = stats['queue']
        print(f"\n📝 PROMPT QUEUE:")
        print(f"   Pending: {queue.get('pending_count', 0)}")
        print(f"   Processing: {queue.get('processing_count', 0)}")
        print(f"   Completed: {queue.get('completed_count', 0)}")
        
        # Model status
        print(f"\n🤖 MODELS:")
        print(f"   Reasoning: {DEFAULT_REASONING_MODEL}")
        print(f"   Vision: {DEFAULT_VISION_MODEL}")
        
        # Recent activity
        print(f"\n📈 RECENT ACTIVITY:")
        # Could add more here with activity tracking
    
    def _progress_bar(self, percentage: float, width: int = 20) -> str:
        """Create a progress bar"""
        filled = int(percentage / 100 * width)
        return "█" * filled + "░" * (width - filled)
    
    def _task_icon(self, status: str) -> str:
        """Get icon for task status"""
        icons = {
            "completed": "✅",
            "in_progress": "⏳",
            "pending": "⚪",
            "blocked": "🚫",
            "cancelled": "❌",
        }
        return icons.get(status, "❓")
    
    def _update_dashboard(self):
        """Update the ASCII dashboard"""
        # Generate dashboard content
        lines = [
            "╔══════════════════════════════════════════════════════════════════════╗",
            "║                    OPENCLAW PROJECT OVERSIGHT                         ║",
            f"║                    Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                       ║",
            "╚══════════════════════════════════════════════════════════════════════╝",
            "",
        ]
        
        # Add project status
        projects = self.aipm.list_projects()
        for p in projects[:5]:
            stats = self.aipm.projects.get_project_stats(p.id)
            bar = self._progress_bar(stats['completion_percentage'])
            lines.append(f"┌─ {p.name} ──────────────────────────────────────────────────┐")
            lines.append(f"│ [{bar}] {stats['completion_percentage']:5.1f}%   │")
            lines.append(f"│ Tasks: {stats['completed']}/{stats['total_tasks']} done │")
            lines.append("└──────────────────────────────────────────────────────────────────┘")
            lines.append("")
        
        # Add queue status
        stats = self.aipm.get_stats()
        queue = stats['queue']
        lines.append("┌─ PROMPT QUEUE ─────────────────────────────────────────────────┐")
        lines.append(f"│ Pending: {queue.get('pending_count', 0):<5} Completed: {queue.get('completed_count', 0):<5}        │")
        lines.append("└──────────────────────────────────────────────────────────────────┘")
        
        # Write dashboard
        dashboard_path = Path.home() / ".aipm" / "ascii" / "oversight_dashboard.ascii"
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text("\n".join(lines))


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    oversight = ProjectOversight()
    command = sys.argv[1]
    
    if command == "status":
        project_name = sys.argv[2] if len(sys.argv) > 2 else None
        oversight.status(project_name)
    
    elif command == "next":
        oversight.next_prompt()
    
    elif command == "process":
        model = None
        use_vision = "--vision" in sys.argv
        
        if "-m" in sys.argv:
            idx = sys.argv.index("-m")
            if idx + 1 < len(sys.argv):
                model = sys.argv[idx + 1]
        
        asyncio.run(oversight.process_next(model=model, use_vision=use_vision))
    
    elif command == "focus":
        if len(sys.argv) < 3:
            print("Usage: python3 openclaw_oversight.py focus <project_name>")
            return
        oversight.focus(sys.argv[2])
    
    elif command == "report":
        oversight.report()
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
