#!/usr/bin/env python3
"""
Roadmap Processor - AIPM Self-Improvement Engine

Parses ROADMAP.md and auto-enqueues tasks for autonomous execution.
Implements the "Ouroboros" goal: AIPM improving itself.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime


@dataclass
class RoadmapTask:
    """A task extracted from roadmap"""
    phase: str
    section: str
    description: str
    priority: int = 5
    completed: bool = False
    metadata: Dict = field(default_factory=dict)


class RoadmapProcessor:
    """
    Parse roadmap and convert to actionable prompts.
    
    Format expected in ROADMAP.md:
    
    ## Phase 1: Name (Q2 2026)
    
    ### 1. Section Name
    * [ ] Task description - priority:1
    * [x] Completed task
    * [ ] Another task
    
    Priority markers:
    - 🔥 or priority:1 = urgent
    - Medium or no marker = priority 5
    - Low = priority 8
    """
    
    PHASE_PATTERN = re.compile(r'^##\s+Phase\s+(\d+)[:\s]+(.+?)(?:\s*\((.+?)\))?$')
    SECTION_PATTERN = re.compile(r'^###\s+(?:\d+\.\s+)?(.+)$')
    TASK_PATTERN = re.compile(r'^[\s]*[*-]\s+\[([ xX])\]\s+(.+)$')
    PRIORITY_PATTERN = re.compile(r'(?:🔥|priority:(\d)|urgent)', re.IGNORECASE)
    
    def __init__(self, roadmap_path: Path, ctrm_db=None, queue_bridge=None):
        self.roadmap_path = Path(roadmap_path)
        self.ctrm = ctrm_db
        self.queue = queue_bridge
        self.tasks: List[RoadmapTask] = []
        
    def parse(self) -> List[RoadmapTask]:
        """Parse roadmap file into structured tasks"""
        if not self.roadmap_path.exists():
            return []
        
        content = self.roadmap_path.read_text()
        lines = content.split('\n')
        
        current_phase = "Unknown"
        current_section = "General"
        
        for line in lines:
            # Check for phase header
            match = self.PHASE_PATTERN.match(line)
            if match:
                current_phase = f"Phase {match.group(1)}: {match.group(2).strip()}"
                continue
            
            # Check for section header
            match = self.SECTION_PATTERN.match(line)
            if match:
                current_section = match.group(1).strip()
                continue
            
            # Check for task
            match = self.TASK_PATTERN.match(line)
            if match:
                completed = match.group(1).lower() == 'x'
                description = match.group(2).strip()
                
                # Extract priority
                priority = 5  # default
                prio_match = self.PRIORITY_PATTERN.search(description)
                if prio_match:
                    if prio_match.group(1):
                        priority = int(prio_match.group(1))
                    else:
                        priority = 1  # 🔥 marker
                
                # Clean description of priority markers
                clean_desc = self.PRIORITY_PATTERN.sub('', description).strip()
                clean_desc = re.sub(r'\s+-\s*$', '', clean_desc)
                
                task = RoadmapTask(
                    phase=current_phase,
                    section=current_section,
                    description=clean_desc,
                    priority=priority,
                    completed=completed,
                    metadata={
                        "source": "roadmap",
                        "roadmap_file": str(self.roadmap_path),
                    }
                )
                self.tasks.append(task)
        
        return self.tasks
    
    def get_pending_tasks(self) -> List[RoadmapTask]:
        """Get tasks that haven't been completed"""
        return [t for t in self.tasks if not t.completed]
    
    def get_tasks_by_phase(self, phase: str) -> List[RoadmapTask]:
        """Filter tasks by phase"""
        return [t for t in self.tasks if phase.lower() in t.phase.lower()]
    
    def enqueue_tasks(self, phase_filter: Optional[str] = None, max_tasks: int = 10) -> int:
        """Enqueue pending tasks to the prompt queue"""
        if not self.ctrm:
            return 0
        
        pending = self.get_pending_tasks()
        
        if phase_filter:
            pending = self.get_tasks_by_phase(phase_filter)
        
        # Sort by priority (lower = higher priority)
        pending.sort(key=lambda t: t.priority)
        pending = pending[:max_tasks]
        
        enqueued = 0
        for task in pending:
            prompt_text = f"[ROADMAP:{task.phase}] {task.section}: {task.description}"
            
            # Enqueue via CTRM manager
            try:
                # Use the CTRMPromptManager's enqueue method
                self.ctrm.enqueue(
                    prompt=prompt_text,
                    priority=task.priority,
                    source="roadmap",
                    metadata={
                        "phase": task.phase,
                        "section": task.section,
                        "source": "roadmap",
                        "original_description": task.description,
                    }
                )
                enqueued += 1
                print(f"  📥 Enqueued: {task.description[:50]}...")
            except Exception as e:
                print(f"  ❌ Failed to enqueue {task.description}: {e}")
        
        return enqueued
    
    def mark_completed(self, task_description: str) -> bool:
        """Mark a task as completed in the roadmap file"""
        if not self.roadmap_path.exists():
            return False
        
        content = self.roadmap_path.read_text()
        
        # Find and update the checkbox
        # Match the task line and change [ ] to [x]
        pattern = rf'(\s*[*-]\s+)\[ \]\s+({re.escape(task_description)})'
        replacement = r'\1[x] \2'
        
        new_content = re.sub(pattern, replacement, content)
        
        if new_content != content:
            self.roadmap_path.write_text(new_content)
            return True
        
        return False
    
    def get_progress_report(self) -> str:
        """Generate progress report"""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.completed)
        pending = total - completed
        
        by_phase = {}
        for task in self.tasks:
            phase = task.phase
            if phase not in by_phase:
                by_phase[phase] = {"total": 0, "completed": 0}
            by_phase[phase]["total"] += 1
            if task.completed:
                by_phase[phase]["completed"] += 1
        
        lines = [
            f"# Roadmap Progress",
            f"",
        ]
        
        if total > 0:
            lines.append(f"**Overall:** {completed}/{total} ({completed/total*100:.0f}%)")
        else:
            lines.append(f"**Overall:** No tasks found")
        lines.append(f"")
        
        for phase, stats in by_phase.items():
            pct = stats["completed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            status = "✅" if pct == 100 else "🔄" if pct > 0 else "⚪"
            lines.append(f"{status} **{phase}**: {stats['completed']}/{stats['total']} ({pct:.0f}%)")
        
        return "\n".join(lines)


# CLI
if __name__ == "__main__":
    import sys
    
    roadmap_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/ROADMAP.md")
    
    processor = RoadmapProcessor(roadmap_path)
    tasks = processor.parse()
    
    print(f"\n📊 Parsed {len(tasks)} tasks from {roadmap_path}")
    print(f"   Pending: {len(processor.get_pending_tasks())}")
    print()
    
    # Group by phase
    by_phase = {}
    for task in processor.get_pending_tasks():
        by_phase.setdefault(task.phase, []).append(task)
    
    for phase, phase_tasks in by_phase.items():
        print(f"\n### {phase}")
        for task in phase_tasks[:5]:  # Show first 5
            status = "✅" if task.completed else "⬜"
            prio = f"🔥" if task.priority <= 2 else ""
            print(f"  {status} [{task.priority}] {task.description[:60]}... {prio}")
    
    print("\n" + processor.get_progress_report())
