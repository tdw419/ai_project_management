"""
OpenSpec Adapter -- extract structured complexity signals from OpenSpec changes.

The model router currently gets raw strings (issue_title, issue_body) and
keyword-matches on them. This adapter reads the rich OpenSpec data that
SpecQueue already parses (proposal, design, tasks, specs) and produces a
TaskContext with concrete, measurable signals:

  - file_count: how many files to create/modify
  - step_count: how many implementation steps
  - has_design_doc: was this thought through before coding?
  - has_requirements: are there formal specs?
  - success_criteria_count: how many acceptance criteria
  - dependency_depth: how deep is the dependency chain
  - component_count: how many components in the design
  - cross_component: does this task touch multiple components?
  - proposal_risk_count: how many risks identified
  - spec_text: raw text for keyword fallback

Usage:
    from .openspec_adapter import extract_task_context

    ctx = extract_task_context(spec_queue_item, change)
    # Pass ctx to model router instead of raw strings
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List

from .spec import Change, ChangeStatus, Task, TaskStatus, TasksDoc
from .spec_queue import SpecQueueItem


@dataclass
class TaskContext:
    """Structured signals extracted from OpenSpec data for routing decisions."""

    # ── Core signals (directly measurable) ─────────────────────────────
    file_count: int = 0
    step_count: int = 0
    has_design_doc: bool = False
    has_requirements: bool = False
    has_specs_dir: bool = False
    spec_dir_count: int = 0

    # ── Proposal signals ──────────────────────────────────────────────
    success_criteria_count: int = 0
    proposal_risk_count: int = 0
    proposal_why_length: int = 0  # chars in "why" section

    # ── Design signals ────────────────────────────────────────────────
    component_count: int = 0
    design_file_change_count: int = 0
    has_data_flow: bool = False
    has_architecture_overview: bool = False

    # ── Dependency signals ────────────────────────────────────────────
    dependency_depth: int = 0  # max depth of depends_on chains
    dependency_count: int = 0  # direct dependencies for this task

    # ── Cross-cutting signals ─────────────────────────────────────────
    cross_component: bool = False  # task files span multiple components
    change_status: str = "draft"
    change_task_count: int = 0  # total tasks in the change
    change_completed_pct: float = 0.0  # % of tasks done

    # ── Text for keyword fallback ─────────────────────────────────────
    task_description: str = ""
    component: str = ""
    change_title: str = ""

    def summary(self) -> str:
        """One-line summary for logging."""
        parts = []
        if self.file_count:
            parts.append(f"{self.file_count} files")
        if self.step_count:
            parts.append(f"{self.step_count} steps")
        if self.has_design_doc:
            parts.append("has-design")
        if self.has_requirements:
            parts.append("has-reqs")
        if self.component_count:
            parts.append(f"{self.component_count} components")
        if self.dependency_count:
            parts.append(f"{self.dependency_count} deps")
        if self.cross_component:
            parts.append("cross-component")
        return f"TaskContext({', '.join(parts) or 'minimal'})"


def extract_task_context(
    item: SpecQueueItem,
    change: Optional[Change] = None,
) -> TaskContext:
    """Extract structured signals from a SpecQueueItem and its parent Change.

    Args:
        item: The spec queue item (task-level data).
        change: The parent Change object (proposal, design, requirements).

    Returns:
        TaskContext with measurable signals for routing.
    """
    ctx = TaskContext()

    # ── From SpecQueueItem (always available) ─────────────────────────
    ctx.file_count = len(item.files) if item.files else 0
    ctx.step_count = len(item.steps) if item.steps else 0
    ctx.dependency_count = len(item.depends_on) if item.depends_on else 0
    ctx.task_description = item.task_description
    ctx.component = item.component
    ctx.change_title = item.change_title

    # ── From Change (if available) ────────────────────────────────────
    if change is None:
        return ctx

    ctx.change_status = change.status.value if change.status else "draft"

    # Proposal signals
    if change.proposal:
        ctx.success_criteria_count = len(change.proposal.success_criteria) if change.proposal.success_criteria else 0
        ctx.proposal_risk_count = len(change.proposal.risks) if change.proposal.risks else 0
        ctx.proposal_why_length = len(change.proposal.why) if change.proposal.why else 0

    # Design signals
    if change.design:
        ctx.has_design_doc = True
        ctx.component_count = len(change.design.components) if change.design.components else 0
        ctx.design_file_change_count = len(change.design.file_changes) if change.design.file_changes else 0
        ctx.has_data_flow = bool(change.design.data_flow)
        ctx.has_architecture_overview = bool(change.design.architecture_overview)

        # Check if task files span multiple components
        if item.files and change.design.components:
            task_components = set()
            for f in item.files:
                for comp in change.design.components:
                    if comp.file_path and f in comp.file_path:
                        task_components.add(comp.name)
                    elif comp.file_path and f.startswith(comp.file_path):
                        task_components.add(comp.name)
            ctx.cross_component = len(task_components) > 1

    # Requirements signals
    if change.requirements:
        ctx.has_requirements = True

    # Tasks signals -- dependency depth and progress
    if change.tasks:
        ctx.change_task_count = change.tasks.total_tasks
        ctx.change_completed_pct = change.tasks.progress_pct

        # Calculate dependency depth for this task
        ctx.dependency_depth = _calc_dependency_depth(
            item.task_id, change.tasks
        )

    return ctx


def _calc_dependency_depth(task_id: str, tasks_doc: TasksDoc) -> int:
    """Calculate the max depth of the dependency chain leading to this task.

    E.g., if TASK-03 depends on TASK-02 which depends on TASK-01, depth = 2.
    """
    task_map = {t.id: t for t in tasks_doc.tasks}

    def depth(tid: str, visited: set) -> int:
        if tid in visited:
            return 0  # circular dep guard
        visited.add(tid)
        task = task_map.get(tid)
        if not task or not task.depends_on:
            return 0
        return 1 + max((depth(d, visited) for d in task.depends_on), default=0)

    return depth(task_id, set())


def has_specs_dir(change_dir) -> bool:
    """Check if the change has a specs/ directory."""
    from pathlib import Path
    if isinstance(change_dir, str):
        change_dir = Path(change_dir)
    specs_dir = change_dir / "specs"
    return specs_dir.exists() and specs_dir.is_dir()


def count_spec_files(change_dir) -> int:
    """Count spec files in the specs/ directory."""
    from pathlib import Path
    if isinstance(change_dir, str):
        change_dir = Path(change_dir)
    specs_dir = change_dir / "specs"
    if not specs_dir.exists():
        return 0
    return len([f for f in specs_dir.iterdir() if f.is_dir() or f.suffix in ('.md', '.yaml', '.yml')])


def extract_task_context_full(
    item: SpecQueueItem,
    change: Optional[Change] = None,
    change_dir=None,
) -> TaskContext:
    """Extract full context including filesystem signals (specs dir count).

    Use this when you have access to the change directory on disk.
    Falls back to extract_task_context() if change_dir is not available.
    """
    ctx = extract_task_context(item, change)

    if change_dir:
        ctx.has_specs_dir = has_specs_dir(change_dir)
        ctx.spec_dir_count = count_spec_files(change_dir)

    return ctx
