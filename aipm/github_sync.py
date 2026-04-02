"""
GitHub sync -- bidirectional sync between AIPM specs and GitHub Issues/Milestones/Labels.

Uses the `gh` CLI. No API token management needed -- just requires
gh to be authenticated (gh auth login).

Features:
- Create/update GitHub Issues from Changes
- Create Milestones from version groups
- Sync labels: spec-defined, in-progress, needs-verification, etc.
- Update issue status when tasks complete
- Close issues when changes complete
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .spec import Change, ChangeStatus, Task, TaskStatus


# ── Label scheme ──────────────────────────────────────────────────────────

LABELS = {
    "spec-defined":      {"color": "0e8a16", "description": "Spec fully defined, ready for implementation"},
    "in-progress":       {"color": "fbca04", "description": "Currently being worked on by pi agent"},
    "needs-verification":{"color": "d93f0b", "description": "Code written, needs test verification"},
    "blocked":           {"color": "b60205", "description": "Blocked by dependency or issue"},
    "circuit-breaker":   {"color": "000000", "description": "Auto-paused due to repeated failures"},
    "autospec":          {"color": "5319e7", "description": "Managed by AIPM autospec"},
    "rca":               {"color": "0052cc", "description": "Root cause analysis issue"},
    "priority:critical": {"color": "ff0000", "description": "HUMAN_URGENT -- always processed first"},
    "priority:high":     {"color": "e11d48", "description": "High priority"},
    "priority:medium":   {"color": "fb923c", "description": "Medium priority"},
    "priority:low":      {"color": "94a3b8", "description": "Low priority"},
}

STATUS_TO_LABELS = {
    ChangeStatus.DRAFT: ["autospec"],
    ChangeStatus.PROPOSED: ["autospec", "spec-defined"],
    ChangeStatus.APPROVED: ["autospec", "spec-defined"],
    ChangeStatus.IN_PROGRESS: ["autospec", "in-progress"],
    ChangeStatus.COMPLETED: ["autospec"],
    ChangeStatus.ARCHIVED: ["autospec"],
}


class GitHubSync:
    """Sync AIPM changes with GitHub Issues."""

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path).resolve()
        self._repo_name: Optional[str] = None

    @property
    def repo_name(self) -> Optional[str]:
        if self._repo_name:
            return self._repo_name
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self._repo_name = result.stdout.strip()
                return self._repo_name
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def is_available(self) -> bool:
        """Check if gh CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    # ── Setup ─────────────────────────────────────────────────────────

    def ensure_labels(self) -> int:
        """Create/update all AIPM labels. Returns count created."""
        created = 0
        for name, config in LABELS.items():
            try:
                result = subprocess.run(
                    [
                        "gh", "label", "create", name,
                        "--color", config["color"],
                        "--description", config["description"],
                        "--force",
                    ],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    created += 1
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return created

    def create_milestone(self, title: str, description: str = "") -> Optional[int]:
        """Create a milestone. Returns milestone number."""
        try:
            cmd = ["gh", "api", "repos/{owner}/{repo}/milestones", "-f", f"title={title}"]
            if description:
                cmd.extend(["-f", f"description={description}"])
            result = subprocess.run(
                cmd, cwd=self.repo_path, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("number")
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return None

    # ── Issue management ──────────────────────────────────────────────

    def create_issue(self, change: Change) -> Optional[int]:
        """Create a GitHub Issue from a Change. Returns issue number."""
        if not self.repo_name:
            return None

        title = f"[Spec] {change.title}"
        body = change.to_markdown()
        labels = STATUS_TO_LABELS.get(change.status, ["autospec"])

        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
        ]
        for label in labels:
            cmd.extend(["--label", label])
        if change.github_milestone:
            cmd.extend(["--milestone", str(change.github_milestone)])

        try:
            result = subprocess.run(
                cmd, cwd=self.repo_path, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                # Parse issue number from URL
                url = result.stdout.strip()
                issue_num = int(url.rstrip("/").split("/")[-1])
                return issue_num
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass
        return None

    def update_issue(self, issue_number: int, change: Change) -> bool:
        """Update an existing issue to reflect change state."""
        if not self.repo_name:
            return False

        labels = STATUS_TO_LABELS.get(change.status, ["autospec"])

        try:
            # Update body
            body = change.to_markdown()
            subprocess.run(
                ["gh", "issue", "edit", str(issue_number), "--body", body],
                cwd=self.repo_path, capture_output=True, text=True, timeout=15,
            )

            # Update labels (remove old AIPM labels, add new ones)
            # First remove all autospec-related labels
            all_aipm_labels = set(LABELS.keys())
            for old_label in all_aipm_labels:
                subprocess.run(
                    ["gh", "issue", "edit", str(issue_number), "--remove-label", old_label],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=10,
                )
            # Add current labels
            for label in labels:
                subprocess.run(
                    ["gh", "issue", "edit", str(issue_number), "--add-label", label],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=10,
                )

            # Close if completed
            if change.status == ChangeStatus.COMPLETED:
                subprocess.run(
                    ["gh", "issue", "close", str(issue_number), "--comment",
                     f"Auto-completed by AIPM. Progress: {change.progress_pct:.0f}%"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=15,
                )

            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def sync_change(self, change: Change) -> Optional[int]:
        """Sync a change with GitHub. Creates or updates the issue.

        Returns the issue number.
        """
        if not self.is_available():
            return None

        if change.github_issue:
            self.update_issue(change.github_issue, change)
            return change.github_issue

        issue_num = self.create_issue(change)
        if issue_num:
            change.github_issue = issue_num
        return issue_num

    # ── Batch operations ──────────────────────────────────────────────

    def sync_all(self, changes: List[Change]) -> Dict[str, int]:
        """Sync all changes. Returns stats: {created, updated, skipped}."""
        stats = {"created": 0, "updated": 0, "skipped": 0}
        for change in changes:
            if change.github_issue:
                if self.update_issue(change.github_issue, change):
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                issue_num = self.create_issue(change)
                if issue_num:
                    change.github_issue = issue_num
                    stats["created"] += 1
                else:
                    stats["skipped"] += 1
        return stats

    def get_milestone_progress(self, milestone_number: int) -> Optional[Dict]:
        """Get progress for a milestone."""
        if not self.repo_name:
            return None
        try:
            result = subprocess.run(
                ["gh", "issue", "list", "--milestone", str(milestone_number),
                 "--state", "all", "--json", "state", "--limit", "100"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                issues = json.loads(result.stdout)
                total = len(issues)
                closed = sum(1 for i in issues if i.get("state") == "CLOSED")
                return {"total": total, "closed": closed, "open": total - closed}
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return None
