from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from .base import SpecDocument


class TaskStatus(str, Enum):
    """Status of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class TaskStep(BaseModel):
    """A step within a task."""

    order: int = Field(..., description="The order of this step within the task")
    action: str = Field(..., description="What action to perform")
    code: Optional[str] = Field(
        default=None, description="Code snippet to execute (if applicable)"
    )
    command: Optional[str] = Field(
        default=None, description="Command to run (if applicable)"
    )
    expected_result: str = Field(
        ..., description="What the expected result of this step is"
    )
    completed: bool = Field(
        default=False, description="Whether this step has been completed"
    )


class Task(BaseModel):
    """A task to be completed."""

    id: str = Field(..., description="Unique identifier for the task")
    component: str = Field(..., description="The component this task belongs to")
    description: str = Field(
        ..., description="Description of what the task accomplishes"
    )
    files: List[str] = Field(
        default_factory=list, description="List of file paths affected by this task"
    )
    steps: List[TaskStep] = Field(
        default_factory=list, description="Steps to complete this task"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING, description="Current status of the task"
    )
    depends_on: List[str] = Field(
        default_factory=list, description="List of task IDs this task depends on"
    )

    @property
    def estimated_minutes(self) -> int:
        """Estimate the time required to complete this task in minutes.

        This is a simple implementation that estimates 10 minutes per step.
        In a real implementation, this could be more sophisticated.
        """
        return len(self.steps) * 10


class TaskDocument(SpecDocument):
    """Model for OpenSpec tasks documents."""

    tasks: List[Task] = Field(default_factory=list, description="List of tasks")

    def get_next_pending(self) -> Optional[Task]:
        """Get the next pending task that has no unmet dependencies.

        Returns:
            The next pending task, or None if no pending tasks are available.
        """
        # Get all pending tasks
        pending_tasks = [
            task for task in self.tasks if task.status == TaskStatus.PENDING
        ]

        # Filter to only those whose dependencies are completed
        available_tasks = []
        for task in pending_tasks:
            dependencies_met = True
            for dep_id in task.depends_on:
                # Find the dependency task
                dep_task = next((t for t in self.tasks if t.id == dep_id), None)
                if dep_task is None or dep_task.status != TaskStatus.COMPLETED:
                    dependencies_met = False
                    break
            if dependencies_met:
                available_tasks.append(task)

        # Return the first available task, or None if none are available
        return available_tasks[0] if available_tasks else None

    def to_markdown(self) -> str:
        """Convert the tasks document to markdown format."""
        lines = ["## Tasks\n"]

        if not self.tasks:
            lines.append("*No tasks defined.*\n")
            return "".join(lines)

        for task in self.tasks:
            # Status icon
            status_icon = {
                TaskStatus.PENDING: "[ ]",
                TaskStatus.IN_PROGRESS: "[>]",
                TaskStatus.COMPLETED: "[x]",
                TaskStatus.BLOCKED: "[!]",
                TaskStatus.FAILED: "[x]",
            }.get(task.status, "[ ]")

            lines.extend(
                [
                    f"### {status_icon} {task.id}: {task.description}\n",
                    f"- **Component**: {task.component}\n",
                ]
            )

            if task.files:
                lines.append(f"- **Files**: {', '.join(task.files)}\n")

            if task.depends_on:
                lines.append(f"- **Depends on**: {', '.join(task.depends_on)}\n")

            if task.steps:
                lines.append("- **Steps**:\n")
                for step in task.steps:
                    step_status = "[x]" if step.completed else "[ ]"
                    lines.append(f"  {step_status} {step.order}. {step.action}\n")
                    if step.code:
                        lines.append(f"    ```\n    {step.code}\n    ```\n")
                    if step.command:
                        lines.append(f"    `$ {step.command}`\n")
                    lines.append(f"    *Expected: {step.expected_result}*\n")
            lines.append("\n")

        return "".join(lines)
