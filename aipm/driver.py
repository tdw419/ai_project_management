import subprocess
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .config import ProjectConfig
from .state import ProjectState
from .spec_discoverer import SpecDiscoverer
from .spec import Change, ChangeStatus, Task, TaskStatus
from .session_historian import SessionHistorian
from .issue_queue import QueueItem


class GroundedDriver:
    """
    Drives a project forward using grounded state and spec-aware prompts.

    If the project has openspec/ changes, prompts are grounded in the spec
    (requirements, design, current task). Otherwise, falls back to the
    feature list from project.yaml.
    """

    def __init__(self, config: ProjectConfig):
        self.config = config
        self.path = Path(config.path).resolve()
        self.name = config.name
        self.spec_discoverer = SpecDiscoverer(self.path)
        self._changes: Optional[List[Change]] = None

    @property
    def changes(self) -> List[Change]:
        if self._changes is None:
            self._changes = self.spec_discoverer.discover()
        return self._changes

    def refresh_specs(self) -> List[Change]:
        """Re-scan for spec changes."""
        self._changes = self.spec_discoverer.discover()
        return self._changes

    def get_active_change(self) -> Optional[Change]:
        """Get the first change that has work to do."""
        for change in self.changes:
            if change.status in (ChangeStatus.APPROVED, ChangeStatus.IN_PROGRESS):
                return change
        # Fall back to proposed
        for change in self.changes:
            if change.status == ChangeStatus.PROPOSED:
                return change
        return None

    def get_next_task(self, change: Optional[Change] = None) -> Optional[Task]:
        """Get the next task to work on."""
        if not change:
            change = self.get_active_change()
        if not change or not change.tasks:
            return None
        return change.current_task

    def capture_state(self) -> ProjectState:
        """Take a snapshot of the project's current state."""
        state = ProjectState(project_id=self.name)

        # 1. Get git state
        try:
            state.commit_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=self.path, text=True
            ).strip()
        except Exception:
            state.commit_hash = "unknown"

        # 2. Run tests
        if self.config.test_command:
            try:
                result = subprocess.run(
                    self.config.test_command,
                    shell=True, cwd=self.path,
                    capture_output=True, text=True, timeout=120
                )
                state.test_output = (result.stdout + "\n" + result.stderr).strip()

                if self.config.test_parser == "regex":
                    regex = self.config.test_parser_config.get("regex", r"(\d+)/(\d+)")
                    match = re.search(regex, state.test_output)
                    if match:
                        state.test_passing = int(match.group(1))
                        state.test_total = int(match.group(2))
                elif self.config.test_parser == "go":
                    state.test_passing, state.test_total = self._parse_go_tests(state.test_output)
                elif self.config.language in ("go",) and self.config.test_parser == "regex":
                    # Auto-detect Go output if parser not explicitly set
                    if "ok\t" in state.test_output or "FAIL\t" in state.test_output:
                        state.test_passing, state.test_total = self._parse_go_tests(state.test_output)
            except subprocess.TimeoutExpired:
                state.test_output = "Test command timed out after 120s"
            except Exception as e:
                state.test_output = f"Error running tests: {e}"

        return state

    def generate_prompt(self, state: ProjectState) -> str:
        """Generate a spec-grounded prompt for the pi agent.

        If specs exist, the prompt includes requirements, design context,
        and the specific task to implement. Otherwise falls back to the
        feature list from project.yaml.
        """
        change = self.get_active_change()
        task = self.get_next_task(change)

        if change and task:
            return self._generate_spec_prompt(state, change, task)

        # Fallback: feature list from config
        return self._generate_feature_prompt(state)

    def generate_prompt_from_issue(self, item: QueueItem, state: Optional[ProjectState] = None) -> str:
        """Generate a prompt from a GitHub Issue (the queue item).

        Uses the issue body as the primary context, enriched with
        local spec data (requirements, design) if available.
        """
        if state is None:
            state = self.capture_state()

        lines = [
            f"### PROJECT: {self.name}",
            f"Path: {self.path}",
            f"Language: {self.config.language}",
            f"Status: {state.test_passing}/{state.test_total} tests passing.",
            f"",
            f"### ISSUE #{item.issue_number}: {item.title}",
        ]

        # Extract the next unchecked task from the issue body
        next_task = item.get_next_unchecked_task()
        if next_task:
            lines.append(f"Current task: {next_task}")

        # Try to enrich with local spec data
        change_id = item.change_id
        matching_change = None
        for change in self.changes:
            if change.id == change_id or change.title.lower() in item.title.lower():
                matching_change = change
                break

        if matching_change:
            # Add requirements
            if matching_change.requirements and matching_change.requirements.requirements:
                lines.append("")
                lines.append("### REQUIREMENTS (from spec)")
                for req in matching_change.requirements.requirements:
                    lines.append(f"- [{req.strength.value}] {req.id}: {req.description}")
                    for sc in req.scenarios:
                        lines.append(f"  - Given: {sc.given}")
                        lines.append(f"  - When: {sc.when}")
                        lines.append(f"  - Then: {sc.then}")

            # Add design context
            if matching_change.design and matching_change.design.file_changes:
                lines.append("")
                lines.append("### DESIGN - File Changes")
                for fc in matching_change.design.file_changes[:10]:
                    lines.append(f"- [{fc.action.value}] {fc.path}: {fc.description}")

        # Always include the full issue body as context
        lines.append("")
        lines.append("### FULL ISSUE CONTEXT")
        lines.append(item.body)

        # Inject session history from prior work on this project/issue
        try:
            historian = SessionHistorian()
            session_ctx = historian.build_context_for_prompt(
                self.name, item.issue_number
            )
            if session_ctx:
                lines.append("")
                lines.append("### SESSION HISTORY (what prior agents learned)")
                lines.append(session_ctx)
        except Exception:
            pass  # Non-critical enrichment; don't block the prompt

        # Instructions
        lines.append("")
        lines.append("### INSTRUCTIONS")
        lines.append(f"1. Explore the codebase in {self.path}")
        if next_task:
            lines.append(f"2. Implement: {next_task}")
        else:
            lines.append(f"2. Implement the next pending task from the issue")
        lines.append(f"3. Verify with: {self.config.test_command or 'tests'}")
        lines.append(f"4. Commit your changes:")
        lines.append(f"   git add -A")
        lines.append(f"   git commit -m \"fix: #{item.issue_number} {item.title[:50].replace(chr(34), chr(39))}\"")
        lines.append(f"5. DO NOT modify protected files or break existing tests")
        if self.config.protected_files:
            lines.append(f"   Protected: {', '.join(self.config.protected_files)}")

        return "\n".join(lines)

    def _generate_spec_prompt(self, state: ProjectState, change: Change, task: Task) -> str:
        """Generate a detailed prompt from spec data."""
        lines = [
            f"### PROJECT: {self.name}",
            f"Path: {self.path}",
            f"Language: {self.config.language}",
            f"Status: {state.test_passing}/{state.test_total} tests passing.",
            f"",
            f"### SPEC: {change.title} ({change.status.value})",
        ]

        # Add requirements context
        if change.requirements and change.requirements.requirements:
            lines.append("")
            lines.append("### REQUIREMENTS")
            for req in change.requirements.requirements:
                lines.append(f"- [{req.strength.value}] {req.id}: {req.description}")
                for sc in req.scenarios:
                    lines.append(f"  - Given: {sc.given}")
                    lines.append(f"  - When: {sc.when}")
                    lines.append(f"  - Then: {sc.then}")

        # Add design context (only relevant file changes)
        if change.design and change.design.file_changes:
            relevant = [fc for fc in change.design.file_changes
                       if task.files and any(f in fc.path for f in task.files)]
            if not relevant:
                relevant = change.design.file_changes[:5]  # Show first 5 if no match

            lines.append("")
            lines.append("### DESIGN - Relevant File Changes")
            for fc in relevant:
                lines.append(f"- [{fc.action.value}] {fc.path}: {fc.description}")

        # Add task details
        lines.append("")
        lines.append(f"### TASK: {task.id} - {task.description}")
        lines.append(f"Component: {task.component}")
        if task.files:
            lines.append(f"Files: {', '.join(task.files)}")
        if task.depends_on:
            lines.append(f"Depends on: {', '.join(task.depends_on)}")

        if task.steps:
            lines.append("")
            lines.append("Steps:")
            for step in task.steps:
                marker = "[DONE]" if step.completed else "[TODO]"
                lines.append(f"  {marker} {step.order}. {step.action}")
                if step.command and not step.completed:
                    lines.append(f"    Command: {step.command}")
                if step.expected_result and not step.completed:
                    lines.append(f"    Expected: {step.expected_result}")

        # Instructions
        lines.append("")
        lines.append("### INSTRUCTIONS")
        lines.append(f"1. Explore the codebase in {self.path}")
        lines.append(f"2. Implement task {task.id} as described above")
        lines.append(f"3. Verify with: {self.config.test_command or 'tests'}")
        lines.append(f"4. Commit your changes:")
        lines.append(f"   git add -A")
        lines.append(f"   git commit -m \"fix: task {task.id}\"")
        lines.append(f"5. DO NOT modify protected files or break existing tests")
        if self.config.protected_files:
            lines.append(f"   Protected: {', '.join(self.config.protected_files)}")

        return "\n".join(lines)

    def _generate_feature_prompt(self, state: ProjectState) -> str:
        """Fallback prompt when no specs exist."""
        next_feature = "next improvement"
        for f in self.config.features:
            if f not in state.features_done:
                next_feature = f
                break

        return f"""### PROJECT: {self.name}
Path: {self.path}
Language: {self.config.language}
Status: {state.test_passing}/{state.test_total} tests passing.

### GOAL: Implement feature: "{next_feature}"

Your task is to:
1. Explore the codebase in {self.path}
2. Implement the "{next_feature}" feature
3. Verify your changes by running: {self.config.test_command or 'tests'}
4. Commit your changes:
   git add -A
   git commit -m "feat: {next_feature}"

You have full access to the project files. Be surgical and efficient."""

    def verify(self, before: ProjectState, after: ProjectState) -> bool:
        """Verify if the project state improved."""
        code_changed = before.commit_hash != after.commit_hash
        tests_improved = after.test_passing > before.test_passing

        # If no tests exist, any commit is a change
        if before.test_total == 0:
             return code_changed

        return code_changed and tests_improved

    @staticmethod
    def _parse_go_tests(output: str) -> tuple:
        """Parse Go test output. Returns (passing, total).

        Go outputs lines like:
          ok      github.com/glyphlang/glyph/pkg/parser   (cached)
          FAIL    github.com/glyphlang/glyph/pkg/wasm     [setup failed]

        Note: Go pads with spaces before the tab, so we see 'ok  \t' not 'ok\t'.
        """
        passing = 0
        total = 0
        for line in output.split('\n'):
            stripped = line.lstrip()
            # Go outputs 'ok  \t...' (padded) or 'ok\t...'
            is_ok = stripped.startswith('ok\t') or (stripped.startswith('ok ') and '\t' in stripped[:10])
            is_fail = stripped.startswith('FAIL\t') or (stripped.startswith('FAIL ') and '\t' in stripped[:10])
            if is_ok:
                total += 1
                passing += 1
            elif is_fail:
                total += 1
        return passing, total
