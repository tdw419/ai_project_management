"""
Spec-driven queue -- reads/writes task status in openspec/ directories.

This is the primary work queue when a project has openspec/ changes.
Falls back to GitHub Issue Queue when no specs exist.
"""

import re
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .spec import Change, ChangeStatus, Task, TaskStatus


@dataclass
class SpecQueueItem:
    """A spec-driven queue item representing a task to work on."""

    project_name: str
    change_id: str
    task_id: str
    change_title: str
    task_description: str
    component: str
    files: List[str]
    steps: List[str]  # List of step descriptions
    status: TaskStatus
    depends_on: List[str]


class SpecQueue:
    """
    Queue that reads from openspec/ changes as the work source.

    Instead of GitHub Issues, this iterates through spec tasks directly.
    Task status is updated in the tasks.md files.
    """

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path).resolve()
        self.openspec_dir = self.project_path / "openspec" / "changes"
        self._changes: Optional[List[Change]] = None

    @property
    def changes(self) -> List[Change]:
        if self._changes is None:
            self._changes = self._discover_changes()
        return self._changes

    def _discover_changes(self) -> List[Change]:
        """Discover all changes in openspec/changes/."""
        if not self.openspec_dir.exists():
            return []

        changes = []
        for change_dir in sorted(self.openspec_dir.iterdir()):
            if not change_dir.is_dir():
                continue
            change = self._load_change(change_dir)
            if change:
                changes.append(change)
        return changes

    def _load_change(self, change_dir: Path) -> Optional[Change]:
        """Load a single change from its directory."""
        # Try status.yaml first, then .openspec.yaml
        status_file = change_dir / "status.yaml"
        openspec_file = change_dir / ".openspec.yaml"

        if status_file.exists():
            with open(status_file) as f:
                data = yaml.safe_load(f) or {}
        elif openspec_file.exists():
            with open(openspec_file) as f:
                raw = f.read()
                # .openspec.yaml may have YAML front matter after a --- separator
                # or just be a flat yaml. Skip any leading non-yaml header lines.
                parts = raw.split("---")
                yaml_text = parts[-1].strip() if len(parts) > 1 else raw
                data = yaml.safe_load(yaml_text) or {}
        else:
            # No status file -- derive from tasks.md completion if it exists
            tasks_path = change_dir / "tasks.md"
            if tasks_path.exists():
                # Check if all tasks are done -> completed, otherwise draft
                text = tasks_path.read_text()
                all_tasks = re.findall(r"-\s*\[([ x])\]", text)
                heading_tasks = re.findall(r"###\s*\[([ x>!-])\]", text)
                total = len(all_tasks) + len(heading_tasks)
                done = all_tasks.count("x") + heading_tasks.count("x")
                if total > 0 and done == total:
                    status = ChangeStatus.COMPLETED
                elif total > 0 and done > 0:
                    status = ChangeStatus.IN_PROGRESS
                else:
                    status = ChangeStatus.DRAFT
                change = Change(
                    id=change_dir.name,
                    title=change_dir.name.replace("-", " ").title(),
                    status=status,
                )
                change.tasks = self._parse_tasks(tasks_path)
                return change
            return None

        change = Change(
            id=data.get("id", change_dir.name),
            title=data.get("title", change_dir.name),
            status=ChangeStatus(data.get("status", "draft")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

        # Load tasks.md if it exists
        tasks_path = change_dir / "tasks.md"
        if tasks_path.exists():
            change.tasks = self._parse_tasks(tasks_path)

        return change

    def _parse_tasks(self, path: Path):
        """Parse tasks from tasks.md file.

        Supports two formats:
        1. Heading-based: ### [x] TASK-01: description  (with **Files**, **Depends on** metadata)
        2. Section-based: ## 1. Section Name  followed by - [x] 1.1 step  sub-items
        """
        from .spec import TasksDoc, Task, TaskStep

        text = path.read_text()
        title = self._extract_title(text) or path.parent.name
        tasks = []

        # ── Format 1: ### [x] TASK-01: description ──
        task_pattern = re.compile(
            r"###\s*\[([ x>!-])\]\s*(\w+)\s*:\s*(.+)", re.MULTILINE
        )
        for m in task_pattern.finditer(text):
            status_char = m.group(1)
            task_id = m.group(2)
            desc = m.group(3).strip()

            status_map = {
                " ": TaskStatus.PENDING,
                "x": TaskStatus.COMPLETED,
                ">": TaskStatus.IN_PROGRESS,
                "!": TaskStatus.BLOCKED,
                "-": TaskStatus.FAILED,
            }
            status = status_map.get(status_char, TaskStatus.PENDING)

            block = self._get_block_after(text, m.start())

            comp_match = re.search(r"\*\*Component\*\*\s*:\s*(.+)", block)
            files_match = re.search(r"\*\*Files\*\*\s*:\s*(.+)", block)
            deps_match = re.search(r"\*\*Depends on\*\*\s*:\s*(.+)", block)

            files = (
                [f.strip() for f in files_match.group(1).split(",")]
                if files_match
                else []
            )
            deps = (
                [d.strip() for d in deps_match.group(1).split(",")]
                if deps_match
                else []
            )

            steps = []
            step_pattern = re.compile(r"\s*\[([ x])\]\s*(\d+)\.\s*(.+)", re.MULTILINE)
            for sm in step_pattern.finditer(block):
                step_completed = sm.group(1) == "x"
                step_order = int(sm.group(2))
                step_action = sm.group(3).strip()
                steps.append(
                    TaskStep(
                        order=step_order,
                        action=step_action,
                        completed=step_completed,
                    )
                )

            tasks.append(
                Task(
                    id=task_id,
                    description=desc,
                    component=comp_match.group(1).strip() if comp_match else "",
                    files=files,
                    steps=steps,
                    status=status,
                    depends_on=deps,
                )
            )

        # If format 1 found tasks, return immediately
        if tasks:
            return TasksDoc(title=title, tasks=tasks)

        # ── Format 2: ## N. Section Name with - [x] N.M step sub-items ──
        # Each ## section becomes a Task, each - [x] sub-item becomes a TaskStep
        section_pattern = re.compile(r"##\s+(\d+)\.\s+(.+)", re.MULTILINE)
        sections = list(section_pattern.finditer(text))

        for idx, m in enumerate(sections):
            section_num = m.group(1)
            section_name = m.group(2).strip()

            # Get block until next ## or end
            start = m.end()
            end = sections[idx + 1].start() if idx + 1 < len(sections) else len(text)
            block = text[start:end]

            # Parse sub-items: - [x] 1.1 step description  (also handles [-] for failed)
            steps = []
            all_done = True
            any_failed = False
            step_pattern = re.compile(r"-\s*\[([ x-])\]\s*(\d+\.(\d+))\s+(.+)", re.MULTILINE)
            for sm in step_pattern.finditer(block):
                step_char = sm.group(1)
                step_checked = step_char == "x"
                if step_char == "-":
                    any_failed = True
                if not step_checked:
                    all_done = False
                step_order = int(sm.group(3))
                step_action = f"{sm.group(2)} {sm.group(4).strip()}"
                steps.append(TaskStep(
                    order=step_order,
                    action=step_action,
                    completed=step_checked,
                ))

            if not steps:
                continue

            # Derive task status from step completion
            if any_failed:
                task_status = TaskStatus.FAILED
            elif all_done:
                task_status = TaskStatus.COMPLETED
            elif any(s.completed for s in steps):
                task_status = TaskStatus.IN_PROGRESS
            else:
                task_status = TaskStatus.PENDING

            tasks.append(Task(
                id=f"SEC-{section_num}",
                description=section_name,
                component="",
                steps=steps,
                status=task_status,
            ))

        return TasksDoc(title=title, tasks=tasks)

    @staticmethod
    def _extract_title(text: str) -> Optional[str]:
        m = re.match(r"#\s+(.+)", text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _get_block_after(text: str, start: int) -> str:
        """Get text from start until next ### heading or end."""
        rest = text[start:]
        next_heading = re.search(r"\n###\s", rest[10:])
        if next_heading:
            return rest[: 10 + next_heading.start()]
        return rest

    def get_pending(self) -> List[SpecQueueItem]:
        """Get all pending tasks from all changes."""
        items = []
        for change in self.changes:
            if not change.tasks:
                continue
            for task in change.tasks.tasks:
                if task.status == TaskStatus.PENDING:
                    # Check dependencies are met
                    deps_met = self._check_dependencies(task, change)
                    if deps_met:
                        items.append(
                            SpecQueueItem(
                                project_name=self.project_path.name,
                                change_id=change.id,
                                task_id=task.id,
                                change_title=change.title,
                                task_description=task.description,
                                component=task.component,
                                files=task.files,
                                steps=[s.action for s in task.steps],
                                status=task.status,
                                depends_on=task.depends_on,
                            )
                        )
                elif task.status == TaskStatus.IN_PROGRESS:
                    items.append(
                        SpecQueueItem(
                            project_name=self.project_path.name,
                            change_id=change.id,
                            task_id=task.id,
                            change_title=change.title,
                            task_description=task.description,
                            component=task.component,
                            files=task.files,
                            steps=[s.action for s in task.steps],
                            status=task.status,
                            depends_on=task.depends_on,
                        )
                    )
        return items

    def _check_dependencies(self, task: Task, change: Change) -> bool:
        """Check if all dependencies for a task are completed."""
        if not task.depends_on:
            return True
        if not change.tasks:
            return False
        for dep_id in task.depends_on:
            dep_task = next((t for t in change.tasks.tasks if t.id == dep_id), None)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    def get_item(self, change_id: str, task_id: str) -> Optional[SpecQueueItem]:
        """Get a specific item by change_id and task_id."""
        for change in self.changes:
            if change.id != change_id:
                continue
            if not change.tasks:
                continue
            for task in change.tasks.tasks:
                if task.id == task_id:
                    return SpecQueueItem(
                        project_name=self.project_path.name,
                        change_id=change.id,
                        task_id=task.id,
                        change_title=change.title,
                        task_description=task.description,
                        component=task.component,
                        files=task.files,
                        steps=[s.action for s in task.steps],
                        status=task.status,
                        depends_on=task.depends_on,
                    )
        return None

    def start_task(self, item: SpecQueueItem) -> bool:
        """Mark a task as in_progress."""
        return self._update_task_status(
            item.change_id, item.task_id, TaskStatus.IN_PROGRESS
        )

    def complete_task(self, item: SpecQueueItem) -> bool:
        """Mark a task as completed."""
        return self._update_task_status(
            item.change_id, item.task_id, TaskStatus.COMPLETED
        )

    def fail_task(self, item: SpecQueueItem) -> bool:
        """Mark a task as failed."""
        return self._update_task_status(item.change_id, item.task_id, TaskStatus.FAILED)

    def _update_task_status(
        self, change_id: str, task_id: str, status: TaskStatus
    ) -> bool:
        """Update task status in tasks.md file.

        Handles both formats:
        - Format 1: ### [x] TASK-01: desc  -> updates the [status] marker
        - Format 2: ## N. Section with - [x] N.M steps  -> checks/unchecks steps
        """
        change_dir = self.openspec_dir / change_id
        tasks_file = change_dir / "tasks.md"
        if not tasks_file.exists():
            return False

        try:
            text = tasks_file.read_text()

            # Format 1: ### [<status>] TASK-ID: description
            status_chars = {
                TaskStatus.PENDING: " ",
                TaskStatus.IN_PROGRESS: ">",
                TaskStatus.COMPLETED: "x",
                TaskStatus.BLOCKED: "!",
                TaskStatus.FAILED: "-",
            }
            new_char = status_chars.get(status, " ")

            # Try Format 1 first
            pattern = rf"(###\s*\[)([ x>!-])(\s*{re.escape(task_id)}\s*:)"
            if re.search(pattern, text):
                replacement = rf"\g<1>{new_char}\g<3>"
                text = re.sub(pattern, replacement, text)
                tasks_file.write_text(text)
                return True

            # Format 2: SEC-N task ID maps to ## N. Section
            # Find the section and update its checkboxes
            sec_match = re.match(r"SEC-(\d+)", task_id)
            if sec_match:
                section_num = sec_match.group(1)
                # Find ## N. Section heading
                section_re = re.compile(
                    rf"##\s+{re.escape(section_num)}\.\s+(.+)", re.MULTILINE
                )
                m = section_re.search(text)
                if not m:
                    return False

                # Find block boundaries
                next_section = re.search(r"\n##\s+\d+\.", text[m.end():])
                block_start = m.end()
                block_end = m.end() + next_section.start() if next_section else len(text)
                block = text[block_start:block_end]

                if status == TaskStatus.COMPLETED:
                    # Check all unchecked steps
                    new_block = re.sub(r"-\s*\[ \]", "- [x]", block)
                elif status == TaskStatus.IN_PROGRESS:
                    # No change to checkboxes, just a status marker
                    new_block = block
                elif status == TaskStatus.FAILED:
                    # Mark all steps as failed [-]
                    new_block = re.sub(r"-\s*\[ \]", "- [-]", block)
                else:
                    new_block = block

                if new_block != block:
                    text = text[:block_start] + new_block + text[block_end:]
                    tasks_file.write_text(text)

                # Also update status.yaml / .openspec.yaml if exists
                self._update_change_status(change_dir, status)
                return True

        except Exception:
            pass
        return False

    def _update_change_status(self, change_dir: Path, task_status: TaskStatus):
        """Update the change-level status file based on task status."""
        for fname in ("status.yaml", ".openspec.yaml"):
            fpath = change_dir / fname
            if fpath.exists():
                try:
                    raw = fpath.read_text()
                    # Handle .openspec.yaml with --- separator
                    if fname == ".openspec.yaml" and "---" in raw:
                        parts = raw.split("---")
                        header = parts[0]
                        yaml_text = parts[-1].strip()
                    else:
                        header = ""
                        yaml_text = raw

                    data = yaml.safe_load(yaml_text) or {}
                    if task_status == TaskStatus.COMPLETED:
                        data["status"] = "completed"
                    elif task_status == TaskStatus.IN_PROGRESS:
                        if data.get("status") not in ("in_progress", "completed"):
                            data["status"] = "in_progress"
                    elif task_status == TaskStatus.FAILED:
                        data["status"] = "in_progress"  # change stays in_progress

                    new_yaml = yaml.dump(data, default_flow_style=False).strip()
                    if header:
                        fpath.write_text(header.strip() + "\n---\n" + new_yaml + "\n")
                    else:
                        fpath.write_text(new_yaml + "\n")
                except Exception:
                    pass

    def stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        pending = 0
        in_progress = 0
        completed = 0
        blocked = 0
        failed = 0

        for change in self.changes:
            if not change.tasks:
                continue
            for task in change.tasks.tasks:
                if task.status == TaskStatus.PENDING:
                    if self._check_dependencies(task, change):
                        pending += 1
                    else:
                        blocked += 1
                elif task.status == TaskStatus.IN_PROGRESS:
                    in_progress += 1
                elif task.status == TaskStatus.COMPLETED:
                    completed += 1
                elif task.status == TaskStatus.BLOCKED:
                    blocked += 1
                elif task.status == TaskStatus.FAILED:
                    failed += 1

        return {
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "blocked": blocked,
            "failed": failed,
            "total": pending + in_progress + completed + blocked + failed,
        }

    def exists(self) -> bool:
        """Check if openspec/ directory exists."""
        return self.openspec_dir.exists()
