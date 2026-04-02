"""
GitHub Issues as the AIPM work queue.

GitHub Issues are the source of truth for:
  - What work exists (open issues with autospec label)
  - What's in progress (in-progress label)
  - What's done (closed issues)

This replaces the SQLite prompt queue. No more two-system sync.

The local SQLite (state.py) still tracks:
  - Circuit breaker state (consecutive failures, health)
  - Test results and commit hashes
  - Those are runtime state that GitHub doesn't have
"""

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .github_sync import GitHubSync, LABELS


# ── Queue item ───────────────────────────────────────────────────────────

@dataclass
class QueueItem:
    """A work item backed by a GitHub Issue."""
    issue_number: int
    project_name: str
    title: str
    body: str
    labels: List[str] = field(default_factory=list)
    state: str = "open"          # open | closed
    milestone: Optional[str] = None
    assignees: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_in_progress(self) -> bool:
        return "in-progress" in self.labels

    @property
    def is_spec_defined(self) -> bool:
        return "spec-defined" in self.labels

    @property
    def is_blocked(self) -> bool:
        return "blocked" in self.labels or "circuit-breaker" in self.labels

    @property
    def priority(self) -> int:
        """Extract numeric priority from labels. Lower = higher priority."""
        for label in self.labels:
            if label.startswith("priority:"):
                return {
                    "critical": 0,
                    "high": 1,
                    "medium": 2,
                    "low": 3,
                }.get(label.split(":")[1], 2)
        return 2  # default medium

    @property
    def is_human_directed(self) -> bool:
        """True if this is human/agent directed (critical or high priority)."""
        return self.priority <= 1

    @property
    def change_id(self) -> str:
        """Extract the openspec change ID from the issue body or title."""
        # Look for change ID in title: [Spec] Title -> or from body metadata
        match = re.search(r'Change ID:\s*(\S+)', self.body)
        if match:
            return match.group(1)
        # Fallback: slug from title
        title = re.sub(r'^\[Spec\]\s*', '', self.title)
        return re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    @property
    def task_checklist(self) -> Tuple[int, int]:
        """Parse task progress from checklist in issue body.
        Returns (completed, total).
        """
        completed = len(re.findall(r'- \[x\]', self.body, re.IGNORECASE))
        total = len(re.findall(r'- \[[ x]\]', self.body, re.IGNORECASE))
        return completed, total

    def get_next_unchecked_task(self) -> Optional[str]:
        """Get the text of the next unchecked checkbox task."""
        for line in self.body.split('\n'):
            if re.match(r'^- \[ \]', line):
                return line.strip()
        return None


# ── GitHub Issue Queue ───────────────────────────────────────────────────

class GitHubIssueQueue:
    """Reads and writes the work queue using GitHub Issues.

    The queue IS GitHub Issues. No local SQLite for work state.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path).resolve()
        self._gh: Optional[GitHubSync] = None
        self._cache: Optional[List[QueueItem]] = None
        self._cache_time: float = 0
        self._cache_label: Optional[str] = None
        self._cache_ttl: float = 300.0  # 5 minutes

    @property
    def gh(self) -> GitHubSync:
        if self._gh is None:
            self._gh = GitHubSync(self.repo_path)
        return self._gh

    def _run_gh(self, args: List[str], timeout: int = 15) -> Optional[str]:
        """Run a gh CLI command and return stdout."""
        try:
            result = subprocess.run(
                ["gh"] + args,
                cwd=self.repo_path, capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    # ── Read operations ──────────────────────────────────────────────

    def list_open(self, label: Optional[str] = None) -> List[QueueItem]:
        """List open issues. Optionally filter by label."""
        # Check cache: valid if same label and within TTL
        if self._cache is not None and self._cache_label == label and (time.time() - self._cache_time) < self._cache_ttl:
            return self._cache

        args = [
            "issue", "list",
            "--state", "open",
            "--label", "autospec",
            "--limit", "100",
            "--json", "number,title,body,labels,state,milestone,assignees,createdAt,updatedAt",
        ]
        if label:
            args.extend(["--label", label])

        output = self._run_gh(args, timeout=20)
        if not output:
            return []

        try:
            issues = json.loads(output)
        except json.JSONDecodeError:
            return []

        items = []
        for i in issues:
            label_names = [l.get("name", "") for l in i.get("labels", [])]
            milestone = i.get("milestone")
            milestone_title = milestone.get("title", "") if milestone else None
            items.append(QueueItem(
                issue_number=i["number"],
                project_name="",  # filled in by caller
                title=i.get("title", ""),
                body=i.get("body", "") or "",
                labels=label_names,
                state=i.get("state", "open"),
                milestone=milestone_title,
                assignees=[a.get("login", "") for a in i.get("assignees", [])],
                created_at=i.get("createdAt", ""),
                updated_at=i.get("updatedAt", ""),
            ))
        # Store in cache
        self._cache = items
        self._cache_time = time.time()
        self._cache_label = label
        return items

    def get_pending(self) -> List[QueueItem]:
        """Get issues that are ready to be picked up (spec-defined, not in-progress)."""
        all_open = self.list_open()
        pending = []
        for item in all_open:
            if item.is_spec_defined and not item.is_in_progress and not item.is_blocked:
                pending.append(item)
        # Sort by priority (lower number = higher priority), then oldest first
        pending.sort(key=lambda i: (i.priority, i.created_at))
        return pending

    def get_in_progress(self) -> List[QueueItem]:
        """Get issues currently being worked on."""
        return [i for i in self.list_open() if i.is_in_progress]

    def get_next(self) -> Optional[QueueItem]:
        """Get the highest priority pending item."""
        pending = self.get_pending()
        return pending[0] if pending else None

    def get_item(self, issue_number: int) -> Optional[QueueItem]:
        """Get a specific issue by number."""
        output = self._run_gh([
            "issue", "view", str(issue_number),
            "--json", "number,title,body,labels,state,milestone,assignees,createdAt,updatedAt",
        ])
        if not output:
            return None
        try:
            i = json.loads(output)
        except json.JSONDecodeError:
            return None

        label_names = [l.get("name", "") for l in i.get("labels", [])]
        milestone = i.get("milestone")
        milestone_title = milestone.get("title", "") if milestone else None
        return QueueItem(
            issue_number=i["number"],
            project_name="",
            title=i.get("title", ""),
            body=i.get("body", "") or "",
            labels=label_names,
            state=i.get("state", "open"),
            milestone=milestone_title,
            assignees=[a.get("login", "") for a in i.get("assignees", [])],
            created_at=i.get("createdAt", ""),
            updated_at=i.get("updatedAt", ""),
        )

    # ── Write operations ─────────────────────────────────────────────

    def invalidate_cache(self):
        """Clear the issue list cache."""
        self._cache = None
        self._cache_time = 0

    def claim(self, item: QueueItem) -> bool:
        """Mark an issue as in-progress (claimed by AIPM)."""
        self.invalidate_cache()
        # Remove spec-defined, add in-progress
        ok = True
        if "spec-defined" in item.labels:
            r = self._run_gh(["issue", "edit", str(item.issue_number),
                              "--remove-label", "spec-defined"])
            if r is not None:
                item.labels.remove("spec-defined")
            else:
                ok = False
        r = self._run_gh(["issue", "edit", str(item.issue_number),
                          "--add-label", "in-progress"])
        if r is not None:
            if "in-progress" not in item.labels:
                item.labels.append("in-progress")
        else:
            ok = False
        return ok

    def complete(self, item: QueueItem, comment: str = "") -> bool:
        """Close an issue as completed."""
        self.invalidate_cache()
        args = ["issue", "close", str(item.issue_number)]
        if comment:
            args.extend(["--comment", comment])
        r = self._run_gh(args)
        if r is not None:
            item.state = "closed"
        return r is not None

    def fail(self, item: QueueItem, reason: str = "") -> bool:
        """Mark an issue as failed (remove in-progress, add needs-verification)."""
        self.invalidate_cache()
        ok = True
        if "in-progress" in item.labels:
            self._run_gh(["issue", "edit", str(item.issue_number),
                          "--remove-label", "in-progress"])
            item.labels.remove("in-progress")
        r = self._run_gh(["issue", "edit", str(item.issue_number),
                          "--add-label", "needs-verification"])
        if r is not None:
            if "needs-verification" not in item.labels:
                item.labels.append("needs-verification")
        else:
            ok = False
        if reason:
            self._run_gh(["issue", "comment", str(item.issue_number),
                          "--body", f"**AIPM run failed:** {reason}"])
        return ok

    def block(self, item: QueueItem, reason: str = "") -> bool:
        """Mark an issue as blocked (circuit breaker)."""
        self.invalidate_cache()
        r = self._run_gh(["issue", "edit", str(item.issue_number),
                          "--add-label", "circuit-breaker"])
        if r is not None:
            if "circuit-breaker" not in item.labels:
                item.labels.append("circuit-breaker")
        if reason:
            self._run_gh(["issue", "comment", str(item.issue_number),
                          "--body", f"**Circuit breaker tripped:** {reason}"])
        return r is not None

    def update_body(self, item: QueueItem, new_body: str) -> bool:
        """Update the issue body (e.g., to check off completed tasks)."""
        r = self._run_gh(["issue", "edit", str(item.issue_number),
                          "--body", new_body])
        if r is not None:
            item.body = new_body
        return r is not None

    def check_task(self, item: QueueItem, task_line: str) -> bool:
        """Check off a specific task in the issue body."""
        # Find the unchecked line and replace it
        new_body = item.body.replace(
            f"- [ ] {task_line}",
            f"- [x] {task_line}"
        )
        if new_body == item.body:
            # Try without prefix
            lines = item.body.split('\n')
            new_lines = []
            changed = False
            for line in lines:
                if not changed and line.strip() == f"- [ ] {task_line}":
                    new_lines.append(f"- [x] {task_line}")
                    changed = True
                else:
                    new_lines.append(line)
            if changed:
                new_body = '\n'.join(new_lines)
            else:
                return False
        return self.update_body(item, new_body)

    def add_comment(self, item: QueueItem, body: str) -> bool:
        """Add a comment to an issue."""
        r = self._run_gh(["issue", "comment", str(item.issue_number),
                          "--body", body])
        return r is not None

    def add_comment_by_number(self, issue_number: int, body: str) -> bool:
        """Add a comment to an issue by number."""
        r = self._run_gh(["issue", "comment", str(issue_number),
                          "--body", body])
        return r is not None

    def create_issue(self, title: str, body: str = "", labels: List[str] = None) -> Optional[int]:
        """Create a new GitHub issue. Returns issue number on success."""
        args = ["issue", "create", "--title", title, "--body", body or ""]
        if labels:
            for label in labels:
                args.extend(["--label", label])
        result = self._run_gh(args, timeout=15)
        if result:
            # gh issue create outputs the URL
            try:
                return int(result.rstrip("/").split("/")[-1])
            except (ValueError, IndexError):
                return None
        return None

    # ── Commit status ────────────────────────────────────────────────

    def set_commit_status(self, commit_sha: str, state: str,
                          description: str, context: str = "AIPM") -> bool:
        """Create a commit status (green/yellow/red checkmark).

        state: success, failure, pending, error
        """
        if not self.gh.repo_name:
            return False

        target_url = f"https://github.com/{self.gh.repo_name}/commit/{commit_sha}"
        try:
            result = subprocess.run(
                ["gh", "api",
                 f"repos/{self.gh.repo_name}/statuses/{commit_sha}",
                 "-f", f"state={state}",
                 "-f", f"target_url={target_url}",
                 "-f", f"description={description}",
                 "-f", f"context={context}",
                 ],
                cwd=self.repo_path, capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        all_open = self.list_open()
        return {
            "total_open": len(all_open),
            "pending": len(self.get_pending()),
            "in_progress": len(self.get_in_progress()),
            "blocked": sum(1 for i in all_open if i.is_blocked),
        }
