"""
Spec discovery -- finds and parses openspec/ directories in managed projects.

Layout per project:
  <project>/openspec/
    changes/
      <change-id>/
        status.yaml          # Change metadata
        proposal.md          # Why + what
        requirements.md      # Formal requirements (optional)
        design.md            # Architecture (optional)
        tasks.md             # Implementation tasks (optional)

Also reads from project.yaml if it has spec-level fields.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional

from .spec import (
    Change, ChangeStatus, Proposal, RequirementsDoc, Requirement,
    ReqStrength, Scenario, DesignDoc, Component, FileChange, FileAction,
    TasksDoc, Task, TaskStep, TaskStatus, LearningsDoc, Learning,
)


class SpecDiscoverer:
    """Scan a project directory for openspec/ changes."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path).resolve()
        self.openspec_dir = self.project_path / "openspec" / "changes"

    def discover(self) -> List[Change]:
        """Find all changes in openspec/changes/."""
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
        # Try status.yaml first, then .openspec.yaml, then derive from tasks.md
        status_file = change_dir / "status.yaml"
        openspec_file = change_dir / ".openspec.yaml"

        if status_file.exists():
            with open(status_file) as f:
                data = yaml.safe_load(f) or {}
        elif openspec_file.exists():
            with open(openspec_file) as f:
                raw = f.read()
                parts = raw.split("---")
                yaml_text = parts[-1].strip() if len(parts) > 1 else raw
                data = yaml.safe_load(yaml_text) or {}
        else:
            # Derive from tasks.md if it exists
            tasks_path = change_dir / "tasks.md"
            if tasks_path.exists():
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
                data = {"id": change_dir.name, "title": change_dir.name.replace("-", " ").title(), "status": status.value}
            else:
                return None

        change = Change(
            id=data.get("id", change_dir.name),
            title=data.get("title", change_dir.name),
            status=ChangeStatus(data.get("status", "draft")),
            github_issue=data.get("github_issue"),
            github_milestone=data.get("github_milestone"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

        # Load sub-documents if they exist
        proposal_path = change_dir / "proposal.md"
        if proposal_path.exists():
            change.proposal = self._parse_proposal(proposal_path)

        req_path = change_dir / "requirements.md"
        if req_path.exists():
            change.requirements = self._parse_requirements(req_path)

        design_path = change_dir / "design.md"
        if design_path.exists():
            change.design = self._parse_design(design_path)

        tasks_path = change_dir / "tasks.md"
        if tasks_path.exists():
            change.tasks = self._parse_tasks(tasks_path)

        learnings_path = change_dir / "learnings.md"
        if learnings_path.exists():
            change.learnings = self._parse_learnings(learnings_path)

        return change

    def _parse_proposal(self, path: Path) -> Proposal:
        text = path.read_text()
        # Extract sections
        why = self._extract_section(text, "Why") or self._extract_section(text, "Motivation") or ""
        whats_changing = self._extract_section(text, "What Changes") or self._extract_section(text, "What") or ""
        title = self._extract_title(text) or path.parent.name

        # Parse success criteria as bullet list
        criteria_text = self._extract_section(text, "Success Criteria") or ""
        criteria = self._parse_bullet_list(criteria_text)

        risks_text = self._extract_section(text, "Risks") or ""
        risks = self._parse_bullet_list(risks_text)

        return Proposal(
            title=title,
            why=why.strip(),
            whats_changing=whats_changing.strip(),
            success_criteria=criteria,
            risks=risks,
        )

    def _parse_requirements(self, path: Path) -> RequirementsDoc:
        text = path.read_text()
        title = self._extract_title(text) or path.parent.name
        reqs = []

        # Find requirement blocks: ### REQ-01: description
        req_pattern = re.compile(r'###\s+(REQ-\w+)\s*:\s*(.+)', re.MULTILINE)
        for m in req_pattern.finditer(text):
            req_id = m.group(1)
            desc = m.group(2).strip()
            # Get the block after this heading until next ### or end
            block = self._get_block_after(text, m.start())

            # Extract strength
            strength = ReqStrength.MUST
            for s in ReqStrength:
                if s.value in block:
                    strength = s
                    break

            # Extract capability line
            cap_match = re.search(r'\*\*Capability\*\*\s*:\s*(.+)', block)
            capability = cap_match.group(1).strip() if cap_match else desc

            # Extract scenarios
            scenarios = []
            given = when = then = None
            for line in block.split('\n'):
                line = line.strip()
                gm = re.match(r'\*?\*?Given\*?\*?\s*:\s*(.+)', line, re.IGNORECASE)
                wm = re.match(r'\*?\*?When\*?\*?\s*:\s*(.+)', line, re.IGNORECASE)
                tm = re.match(r'\*?\*?Then\*?\*?\s*:\s*(.+)', line, re.IGNORECASE)
                if gm:
                    given = gm.group(1).strip()
                elif wm:
                    when = wm.group(1).strip()
                elif tm:
                    then = tm.group(1).strip()
                    if given and when:
                        scenarios.append(Scenario(given=given, when=when, then=then))
                        given = when = then = None

            reqs.append(Requirement(
                id=req_id, capability=capability, strength=strength,
                description=desc, scenarios=scenarios,
            ))

        return RequirementsDoc(title=title, requirements=reqs)

    def _parse_design(self, path: Path) -> DesignDoc:
        text = path.read_text()
        title = self._extract_title(text) or path.parent.name

        overview = self._extract_section(text, "Architecture Overview") or ""
        components = []

        # Parse component blocks: ### ComponentName
        comp_pattern = re.compile(r'###\s+(\w+)\s*\n', re.MULTILINE)
        for m in comp_pattern.finditer(text):
            name = m.group(1)
            if name.lower() in ("architecture overview", "data flow", "file changes", "migration"):
                continue
            block = self._get_block_after(text, m.start())

            resp_match = re.search(r'\*\*Responsibility\*\*\s*:\s*(.+)', block)
            file_match = re.search(r'\*\*File\*\*\s*:\s*(.+)', block)
            dep_match = re.search(r'\*\*Depends on\*\*\s*:\s*(.+)', block)

            components.append(Component(
                name=name,
                responsibility=resp_match.group(1).strip() if resp_match else "",
                file_path=file_match.group(1).strip() if file_match else None,
                dependencies=[d.strip() for d in dep_match.group(1).split(",")] if dep_match else [],
            ))

        # Parse file changes
        file_changes = []
        fc_pattern = re.compile(r'-\s*\*\*(create|modify|delete)\*\*\s*`([^`]+)`\s*:\s*(.+)', re.IGNORECASE)
        for m in fc_pattern.finditer(text):
            file_changes.append(FileChange(
                action=FileAction(m.group(1).lower()),
                path=m.group(2),
                description=m.group(3).strip(),
            ))

        data_flow = self._extract_section(text, "Data Flow") or ""

        return DesignDoc(
            title=title, architecture_overview=overview.strip(),
            components=components, data_flow=data_flow.strip(),
            file_changes=file_changes,
        )

    def _parse_tasks(self, path: Path) -> TasksDoc:
        text = path.read_text()
        title = self._extract_title(text) or path.parent.name
        tasks = []

        # Parse task blocks: ### [status] TASK-01: description
        task_pattern = re.compile(r'###\s*\[([ x>!-])\]\s*(\w+)\s*:\s*(.+)', re.MULTILINE)
        for m in task_pattern.finditer(text):
            status_char = m.group(1)
            task_id = m.group(2)
            desc = m.group(3).strip()

            status_map = {
                " ": TaskStatus.PENDING, "x": TaskStatus.COMPLETED,
                ">": TaskStatus.IN_PROGRESS, "!": TaskStatus.BLOCKED,
                "-": TaskStatus.FAILED,
            }
            status = status_map.get(status_char, TaskStatus.PENDING)

            block = self._get_block_after(text, m.start())

            comp_match = re.search(r'\*\*Component\*\*\s*:\s*(.+)', block)
            files_match = re.search(r'\*\*Files\*\*\s*:\s*(.+)', block)
            deps_match = re.search(r'\*\*Depends on\*\*\s*:\s*(.+)', block)
            issue_match = re.search(r'\*\*GitHub Issue\*\*\s*:\s*#?(\d+)', block)

            files = [f.strip() for f in files_match.group(1).split(",")] if files_match else []
            deps = [d.strip() for d in deps_match.group(1).split(",")] if deps_match else []

            # Parse steps
            steps = []
            step_pattern = re.compile(r'\s*\[([ x])\]\s*(\d+)\.\s*(.+)', re.MULTILINE)
            for sm in step_pattern.finditer(block):
                step_completed = sm.group(1) == "x"
                step_order = int(sm.group(2))
                step_action = sm.group(3).strip()
                steps.append(TaskStep(
                    order=step_order, action=step_action,
                    completed=step_completed,
                ))

            tasks.append(Task(
                id=task_id, description=desc,
                component=comp_match.group(1).strip() if comp_match else "",
                files=files, steps=steps, status=status,
                depends_on=deps,
                github_issue=int(issue_match.group(1)) if issue_match else None,
            ))

        return TasksDoc(title=title, tasks=tasks)

    def _parse_learnings(self, path: Path) -> LearningsDoc:
        """Parse learnings.md into a LearningsDoc.

        Format:
        # Learnings: Title

        ## constraint

        - **[constraint]** (from TASK-01) Texture memory is not randomly accessible
        - **[constraint]** (from TASK-03) GPU texture size must be power-of-2

        ## discovery

        - **[discovery]** VFS inode table fits in shared memory region 0x100

        ## failure-mode

        - **[failure-mode]** (from TASK-02) Path resolver fails on nested directories

        ## pattern

        - **[pattern]** All shader modules follow init/update/render lifecycle
        """
        text = path.read_text()
        title = self._extract_title(text) or path.parent.name

        learnings = []
        # Match: - **[category]** (from TASK-XX) content
        # or:  - **[category]** content
        pattern = re.compile(
            r'-\s*\*\*\[(\w[\w-]*)\]\*\s*'
            r'(?:\(from\s+(\w+)\)\s+)?'
            r'(.+)',
        )
        for m in pattern.finditer(text):
            category = m.group(1)
            task_id = m.group(2) or ""
            content = m.group(3).strip()
            learnings.append(Learning(
                task_id=task_id,
                category=category,
                content=content,
                change_id="",
            ))

        return LearningsDoc(title=title, learnings=learnings)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_title(text: str) -> Optional[str]:
        m = re.match(r'#\s+(.+)', text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_section(text: str, heading: str) -> Optional[str]:
        pattern = re.compile(
            rf'##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)',
            re.DOTALL | re.IGNORECASE,
        )
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _get_block_after(text: str, start: int) -> str:
        """Get text from start until next ### heading or end."""
        rest = text[start:]
        next_heading = re.search(r'\n###\s', rest[10:])  # skip current heading line
        if next_heading:
            return rest[:10 + next_heading.start()]
        return rest

    @staticmethod
    def _parse_bullet_list(text: str) -> List[str]:
        items = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                items.append(line[2:].strip())
        return items
