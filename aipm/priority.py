"""
Priority Injection System -- human-directed work takes precedence over autonomous tasks.

Since V2 uses GitHub Issues as the queue, priority injection works by:
  1. Creating issues with special labels (priority:critical, priority:high)
  2. Using a control file (.loop.control) for runtime pause/resume
  3. Making get_next() always prefer critical > high > medium > low

Priority tiers (label-based):
  priority:critical  -- HUMAN_URGENT, always processed first
  priority:high      -- human/agent directed
  priority:medium    -- normal autonomous (default)
  priority:low       -- background/batch

Control file ($DATA_DIR/.loop.control):
  {"command": "pause_autonomous"}  -- only process priority:critical/high
  {"command": "resume_autonomous"} -- back to normal
  {"command": "inject_priority"}   -- interrupt: process this issue next
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from .config import DATA_DIR


CONTROL_FILE = DATA_DIR / ".loop.control"


# ── Control file helpers ────────────────────────────────────────────────

def read_control() -> Optional[Dict]:
    """Read the current control file, or None if absent/corrupt."""
    if not CONTROL_FILE.exists():
        return None
    try:
        return json.loads(CONTROL_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write_control(command: str, **extra) -> None:
    """Write a control command."""
    data = {"command": command, "timestamp": datetime.now().isoformat(), **extra}
    CONTROL_FILE.write_text(json.dumps(data, indent=2))


def clear_control() -> None:
    """Remove the control file."""
    if CONTROL_FILE.exists():
        CONTROL_FILE.unlink()


def is_paused() -> bool:
    """Check if autonomous processing is paused."""
    ctrl = read_control()
    if not ctrl:
        return False
    return ctrl.get("command") == "pause_autonomous"


def get_inject_target() -> Optional[int]:
    """Check if there's a specific issue to process next (bypass mode).

    Returns the issue number to prioritize, or None.
    """
    ctrl = read_control()
    if not ctrl:
        return None
    if ctrl.get("command") == "inject_priority":
        return ctrl.get("issue_number")
    return None


# ── PriorityInjector ────────────────────────────────────────────────────

class PriorityInjector:
    """Inject high-priority work into the AIPM loop.

    Uses GitHub Issues + a local control file.
    """

    def __init__(self, queue=None):
        """
        Args:
            queue: GitHubIssueQueue instance for the target project.
                   If None, inject won't create issues (control-file only).
        """
        self.queue = queue

    def inject(
        self,
        title: str,
        body: str = "",
        priority: str = "critical",
        bypass: bool = False,
        source: str = "human",
    ) -> Optional[int]:
        """Inject a high-priority issue into the queue.

        Args:
            title: Issue title
            body: Issue body (markdown)
            priority: Label tier -- "critical", "high", "medium", "low"
            bypass: If True, set control to process this issue immediately
                    even if autonomous work is running
            source: Who injected this (for tracking)

        Returns:
            Issue number on success, None on failure
        """
        if not self.queue:
            print("ERROR: No queue configured for injection")
            return None

        labels = ["autospec", "spec-defined", f"priority:{priority}"]

        # Add source metadata to body
        enriched_body = body or ""
        if source != "human":
            enriched_body += f"\n\n---\n_Injected by: {source}_"

        issue_num = self.queue.create_issue(
            title=title,
            body=enriched_body,
            labels=labels,
        )

        if not issue_num:
            print(f"ERROR: Failed to create issue")
            return None

        tier = priority.upper()
        print(f"Injected #{issue_num}: {title}")
        print(f"  Priority: {tier}, Source: {source}, Bypass: {bypass}")

        # If bypass, set control to force this issue next
        if bypass:
            write_control(
                "inject_priority",
                issue_number=issue_num,
                priority=priority,
                source=source,
            )
            print(f"  BYPASS: set control to process #{issue_num} next")

        return issue_num

    def pause(self, reason: str = "") -> None:
        """Pause autonomous processing. Only critical/high priority issues get picked up."""
        write_control("pause_autonomous", reason=reason)
        print("PAUSED autonomous processing")
        print("  Only priority:critical and priority:high issues will be processed")
        if reason:
            print(f"  Reason: {reason}")

    def resume(self) -> None:
        """Resume autonomous processing."""
        write_control("resume_autonomous")
        print("RESUMED autonomous processing")

        # Clear after a short delay so the loop sees it
        # (the loop will also clear it on next read)
        import time
        time.sleep(0.1)
        clear_control()

    def boost(self, issue_number: int, new_priority: str = "critical") -> bool:
        """Boost an existing issue to higher priority.

        Args:
            issue_number: The issue to boost
            new_priority: "critical", "high", "medium", "low"

        Returns:
            True if successful
        """
        if not self.queue:
            print("ERROR: No queue configured")
            return False

        # Remove old priority labels, add new one
        item = self.queue.get_item(issue_number)
        if not item:
            print(f"ERROR: Issue #{issue_number} not found")
            return False

        # Remove existing priority labels
        for label in item.labels:
            if label.startswith("priority:"):
                self.queue._run_gh([
                    "issue", "edit", str(issue_number),
                    "--remove-label", label,
                ])

        # Add new priority label
        result = self.queue._run_gh([
            "issue", "edit", str(issue_number),
            "--add-label", f"priority:{new_priority}",
        ])

        if result is not None:
            print(f"Boosted #{issue_number} to priority:{new_priority}")
            return True
        else:
            print(f"Failed to boost #{issue_number}")
            return False

    def list_injected(self) -> List[Dict]:
        """List all critical/high priority issues that are pending."""
        if not self.queue:
            return []

        items = self.queue.get_pending()
        high_priority = [
            {
                "number": i.issue_number,
                "title": i.title,
                "priority": next(
                    (l for l in i.labels if l.startswith("priority:")),
                    "priority:medium"
                ),
            }
            for i in items
            if i.priority <= 1  # critical=0 or high=1
        ]
        return high_priority


# ── Agent helper ────────────────────────────────────────────────────────

def inject_agent_task(
    queue,
    title: str,
    body: str = "",
    agent_id: str = "external-agent",
) -> Optional[int]:
    """Convenience: inject a task from an external agent at critical priority.

    Args:
        queue: GitHubIssueQueue instance
        title: Issue title
        body: Issue body
        agent_id: Source agent identifier

    Returns:
        Issue number on success
    """
    injector = PriorityInjector(queue)
    return injector.inject(
        title=title,
        body=body,
        priority="critical",
        bypass=True,
        source=f"agent:{agent_id}",
    )
