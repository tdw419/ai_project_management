"""
Spec models for AIPM v2.

Adapted from autospec but using only dataclasses + stdlib.
No pydantic dependency.

Lifecycle: proposal -> requirements -> design -> tasks -> execution
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────

class ChangeStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ReqStrength(str, Enum):
    MUST = "MUST"
    SHALL = "SHALL"
    SHOULD = "SHOULD"
    MAY = "MAY"


class FileAction(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


# ── Leaf models ────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    given: str
    when: str
    then: str


@dataclass
class Requirement:
    id: str
    capability: str
    strength: ReqStrength = ReqStrength.MUST
    description: str = ""
    scenarios: List[Scenario] = field(default_factory=list)


@dataclass
class Component:
    name: str
    responsibility: str
    file_path: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class FileChange:
    path: str
    action: FileAction = FileAction.MODIFY
    description: str = ""
    lines: Optional[int] = None


@dataclass
class TaskStep:
    order: int
    action: str
    expected_result: str = ""
    code: Optional[str] = None
    command: Optional[str] = None
    completed: bool = False


@dataclass
class Task:
    id: str
    component: str
    description: str
    files: List[str] = field(default_factory=list)
    steps: List[TaskStep] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    depends_on: List[str] = field(default_factory=list)
    github_issue: Optional[int] = None  # linked GitHub issue number

    @property
    def estimated_minutes(self) -> int:
        return len(self.steps) * 10 if self.steps else 15

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0 if self.status == TaskStatus.PENDING else 100.0
        done = sum(1 for s in self.steps if s.completed)
        return (done / len(self.steps)) * 100


# ── Document models ───────────────────────────────────────────────────────

@dataclass
class Learning:
    """A single learning captured from executing a task."""
    task_id: str
    category: str  # "constraint", "pattern", "failure-mode", "discovery"
    content: str
    change_id: str = ""
    discovered_at: str = ""

    def to_markdown(self) -> str:
        lines = [f"- **[{self.category}]** {self.content}\n"]
        if self.task_id:
            lines[0] = f"- **[{self.category}]** (from {self.task_id}) {self.content}\n"
        return "".join(lines)


@dataclass
class LearningsDoc:
    """Accumulated learnings from executing tasks in this change.

    Lives as learnings.md in the change directory. Grows as tasks complete
    and agents discover things the spec didn't predict.
    """
    title: str
    learnings: List[Learning] = field(default_factory=list)

    def add(self, category: str, content: str, task_id: str = "", change_id: str = ""):
        from datetime import datetime
        self.learnings.append(Learning(
            task_id=task_id,
            category=category,
            content=content,
            change_id=change_id,
            discovered_at=datetime.now().isoformat(),
        ))

    @property
    def count(self) -> int:
        return len(self.learnings)

    def by_category(self, category: str) -> List[Learning]:
        return [l for l in self.learnings if l.category == category]

    def to_markdown(self) -> str:
        lines = [f"# Learnings: {self.title}\n\n"]
        if not self.learnings:
            lines.append("_No learnings recorded yet._\n")
            return "".join(lines)

        # Group by category
        categories = {}
        for l in self.learnings:
            categories.setdefault(l.category, []).append(l)

        for cat, items in categories.items():
            lines.append(f"## {cat.title()}\n\n")
            for item in items:
                lines.append(item.to_markdown())
            lines.append("\n")

        return "".join(lines)

    def to_prompt_context(self, max_items: int = 10) -> str:
        """Render learnings as compact context for prompts.

        This is what gets injected into the next agent's prompt.
        """
        if not self.learnings:
            return ""

        lines = [f"### Learnings from previous tasks ({len(self.learnings)} total)\n"]

        # Prioritize: constraints first (don't violate these),
        # then failure modes (don't repeat these),
        # then discoveries (useful context),
        # then patterns (helpful reference)
        priority = {"constraint": 0, "failure-mode": 1, "discovery": 2, "pattern": 3}
        sorted_learnings = sorted(
            self.learnings,
            key=lambda l: priority.get(l.category, 99)
        )

        for l in sorted_learnings[:max_items]:
            source = f" (from {l.task_id})" if l.task_id else ""
            lines.append(f"- [{l.category}]{source}: {l.content}")

        return "\n".join(lines)


@dataclass
class Proposal:
    title: str
    why: str
    whats_changing: str
    success_criteria: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    version: str = "1.0"

    def to_markdown(self) -> str:
        lines = [f"# Proposal: {self.title}\n\n"]
        lines.append(f"## Why\n\n{self.why}\n\n")
        lines.append(f"## What Changes\n\n{self.whats_changing}\n\n")
        if self.success_criteria:
            lines.append("## Success Criteria\n\n")
            for c in self.success_criteria:
                lines.append(f"- {c}\n")
            lines.append("\n")
        if self.risks:
            lines.append("## Risks\n\n")
            for r in self.risks:
                lines.append(f"- {r}\n")
            lines.append("\n")
        return "".join(lines)


@dataclass
class RequirementsDoc:
    title: str
    requirements: List[Requirement] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Requirements: {self.title}\n\n"]
        for req in self.requirements:
            lines.append(f"### {req.id}: {req.description}\n")
            lines.append(f"- **Capability**: {req.capability}\n")
            lines.append(f"- **Strength**: {req.strength.value}\n\n")
            for sc in req.scenarios:
                lines.append(f"  - **Given**: {sc.given}\n")
                lines.append(f"  - **When**: {sc.when}\n")
                lines.append(f"  - **Then**: {sc.then}\n")
            lines.append("\n")
        return "".join(lines)


@dataclass
class DesignDoc:
    title: str
    architecture_overview: str = ""
    components: List[Component] = field(default_factory=list)
    data_flow: str = ""
    file_changes: List[FileChange] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Design: {self.title}\n\n"]
        lines.append(f"## Architecture Overview\n\n{self.architecture_overview}\n\n")
        for comp in self.components:
            lines.append(f"### {comp.name}\n")
            lines.append(f"- **Responsibility**: {comp.responsibility}\n")
            if comp.file_path:
                lines.append(f"- **File**: {comp.file_path}\n")
            if comp.dependencies:
                lines.append(f"- **Depends on**: {', '.join(comp.dependencies)}\n")
            lines.append("\n")
        if self.data_flow:
            lines.append(f"## Data Flow\n\n{self.data_flow}\n\n")
        if self.file_changes:
            lines.append("## File Changes\n\n")
            for fc in self.file_changes:
                lines.append(f"- **{fc.action.value}** `{fc.path}`: {fc.description}\n")
            lines.append("\n")
        return "".join(lines)


@dataclass
class TasksDoc:
    title: str
    tasks: List[Task] = field(default_factory=list)

    def get_next_pending(self) -> Optional[Task]:
        """Get the next pending task with all dependencies met."""
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                any(t.id == dep and t.status == TaskStatus.COMPLETED for t in self.tasks)
                for dep in task.depends_on
            )
            if deps_met:
                return task
        return None

    def get_in_progress(self) -> Optional[Task]:
        for task in self.tasks:
            if task.status == TaskStatus.IN_PROGRESS:
                return task
        return None

    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)

    @property
    def progress_pct(self) -> float:
        if not self.tasks:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    def to_markdown(self) -> str:
        lines = [f"# Tasks: {self.title}\n\n"]
        icons = {
            TaskStatus.PENDING: "[ ]",
            TaskStatus.IN_PROGRESS: "[>]",
            TaskStatus.COMPLETED: "[x]",
            TaskStatus.BLOCKED: "[!]",
            TaskStatus.FAILED: "[-]",
        }
        for task in self.tasks:
            icon = icons.get(task.status, "[ ]")
            lines.append(f"### {icon} {task.id}: {task.description}\n")
            lines.append(f"- **Component**: {task.component}\n")
            if task.files:
                lines.append(f"- **Files**: {', '.join(task.files)}\n")
            if task.depends_on:
                lines.append(f"- **Depends on**: {', '.join(task.depends_on)}\n")
            if task.github_issue:
                lines.append(f"- **GitHub Issue**: #{task.github_issue}\n")
            for step in task.steps:
                sc = "[x]" if step.completed else "[ ]"
                lines.append(f"  {sc} {step.order}. {step.action}\n")
                if step.command:
                    lines.append(f"    `$ {step.command}`\n")
            lines.append("\n")
        lines.append(f"\n**Progress: {self.completed_tasks}/{self.total_tasks} ({self.progress_pct:.0f}%)**\n")
        return "".join(lines)


# ── Change (the top-level container) ──────────────────────────────────────

@dataclass
class Change:
    """A single spec-driven change in a project."""
    id: str
    title: str
    status: ChangeStatus = ChangeStatus.DRAFT
    proposal: Optional[Proposal] = None
    requirements: Optional[RequirementsDoc] = None
    design: Optional[DesignDoc] = None
    learnings: Optional[LearningsDoc] = None
    tasks: Optional[TasksDoc] = None
    github_issue: Optional[int] = None
    github_milestone: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def progress_pct(self) -> float:
        if self.tasks:
            return self.tasks.progress_pct
        status_progress = {
            ChangeStatus.DRAFT: 0,
            ChangeStatus.PROPOSED: 10,
            ChangeStatus.APPROVED: 20,
            ChangeStatus.IN_PROGRESS: 50,
            ChangeStatus.COMPLETED: 100,
            ChangeStatus.ARCHIVED: 100,
        }
        return status_progress.get(self.status, 0)

    @property
    def current_task(self) -> Optional[Task]:
        if not self.tasks:
            return None
        in_progress = self.tasks.get_in_progress()
        if in_progress:
            return in_progress
        return self.tasks.get_next_pending()

    def to_markdown(self) -> str:
        lines = [f"# Change: {self.title}\n\n"]
        lines.append(f"- **ID**: {self.id}\n")
        lines.append(f"- **Status**: {self.status.value}\n")
        lines.append(f"- **Progress**: {self.progress_pct:.0f}%\n")
        if self.github_issue:
            lines.append(f"- **GitHub Issue**: #{self.github_issue}\n")
        lines.append("\n---\n\n")
        if self.proposal:
            lines.append(self.proposal.to_markdown())
            lines.append("\n---\n\n")
        if self.requirements:
            lines.append(self.requirements.to_markdown())
            lines.append("\n---\n\n")
        if self.design:
            lines.append(self.design.to_markdown())
            lines.append("\n---\n\n")
        if self.tasks:
            lines.append(self.tasks.to_markdown())
        if self.learnings and self.learnings.learnings:
            lines.append("\n---\n\n")
            lines.append(self.learnings.to_markdown())
        return "".join(lines)
