"""
Learnings module.

Two responsibilities:
1. Write learnings to the change directory after task outcomes
2. Collect related learnings from other changes for the current change's prompt
"""

from pathlib import Path
from typing import List, Optional
from datetime import datetime
import re

from .spec import LearningsDoc, Learning
from .outcome import PiOutcome, OutcomeStatus


def write_learnings(
    change_dir: Path,
    task_id: str,
    outcome: PiOutcome,
    change_id: str = "",
    project_language: str = "",
) -> bool:
    """Write learnings to learnings.md after a task completes.

    Extracts insights from the outcome -- what worked, what didn't,
    what constraints were discovered -- and appends them
    to the change's learnings.md.

    Returns True if any learnings were written.
    """
    if not change_dir.exists():
        return False

    learnings_path = change_dir / "learnings.md"
    new_entries: List[Learning] = []

    # -- Failure-mode learnings from errors --
    if outcome.errors:
        for err in outcome.errors[:3]:
            new_entries.append(Learning(
                task_id=task_id,
                category="failure-mode",
                content=f"Error encountered: {err[:200]}",
                change_id=change_id,
                discovered_at=datetime.now().isoformat(),
            ))

    # -- Constraint learnings from trust violations --
    if outcome.trust_violations:
        for v in outcome.trust_violations:
            new_entries.append(Learning(
                task_id=task_id,
                category="constraint",
                content=f"Protected file boundary: {v}",
                change_id=change_id,
                discovered_at=datetime.now().isoformat(),
            ))

    # -- Pattern learnings from successful file changes --
    if outcome.status == OutcomeStatus.SUCCESS and outcome.file_changes:
        for fc in outcome.file_changes[:5]:
            new_entries.append(Learning(
                task_id=task_id,
                category="pattern",
                content=f"[{fc.action}] {fc.path}",
                change_id=change_id,
                discovered_at=datetime.now().isoformat(),
            ))

    # -- Discovery learnings from strategy detection --
    if outcome.strategy_detected:
        new_entries.append(Learning(
            task_id=task_id,
            category="discovery",
            content=f"Agent strategy: {outcome.strategy_detected}",
            change_id=change_id,
            discovered_at=datetime.now().isoformat(),
        ))

    # -- Test delta as discovery --
    if outcome.test_delta != 0:
        direction = "improved" if outcome.test_delta > 0 else "regressed"
        new_entries.append(Learning(
            task_id=task_id,
            category="discovery",
            content=(
                f"Tests {direction} by {abs(outcome.test_delta)} "
                f"({outcome.tests_before.passing} -> {outcome.tests_after.passing})"
            ),
            change_id=change_id,
            discovered_at=datetime.now().isoformat(),
        ))

    if not new_entries:
        return False

    # Read existing or create fresh
    if learnings_path.exists():
        text = learnings_path.read_text()
    else:
        text = f"# Learnings: {change_id or change_dir.name}\n\n"

    # Append entries grouped by category
    categories_seen = set(re.findall(r'## (\w[\w-]*)', text))

    for entry in new_entries:
        if entry.category not in categories_seen:
            text += f"\n## {entry.category}\n"
            categories_seen.add(entry.category)
        source = f"(from {entry.task_id}) " if entry.task_id else ""
        text += f"\n- **[{entry.category}]** {source}{entry.content}\n"

    learnings_path.write_text(text)
    return True


def collect_related_learnings(
    changes_dir: Path,
    current_change_id: str,
    max_changes: int = 5,
    max_learnings: int = 15,
) -> str:
    """Collect learnings from OTHER changes in the same project.

    When building a prompt for change X, we include learnings
    from changes Y and Z that have already completed tasks.
    This is the cross-pollination mechanism.

    Returns a context string for injection into prompts.
    """
    if not changes_dir.exists():
        return ""

    all_learnings: List[Learning] = []

    # Scan each change directory for learnings.md
    for change_path in sorted(changes_dir.iterdir()):
        if not change_path.is_dir():
            continue
        if change_path.name == current_change_id:
            continue  # Skip self -- own learnings handled separately

        learnings_file = change_path / "learnings.md"
        if not learnings_file.exists():
            continue

        # Parse learnings from the file
        try:
            text = learnings_file.read_text()
            parsed = _parse_learnings_text(text, change_path.name)
            all_learnings.extend(parsed)
        except Exception:
            continue

        if len(all_learnings) >= max_learnings * 2:
            break

    if not all_learnings:
        return ""

    lines = [f"### Cross-change learnings from this project ({len(all_learnings)} total)\n"]

    # Prioritize: constraints > failure-modes > discoveries > patterns
    priority = {"constraint": 0, "failure-mode": 1, "discovery": 2, "pattern": 3}
    sorted_l = sorted(all_learnings, key=lambda l: priority.get(l.category, 99))

    for l in sorted_l[:max_learnings]:
        source = f" ({l.change_id})" if l.change_id else ""
        lines.append(f"- [{l.category}]{source}: {l.content}")

    return "\n".join(lines)


def _parse_learnings_text(text: str, change_id: str) -> List[Learning]:
    """Parse learnings from a learnings.md file.

    Format:
    - **[category]** content
    - **[category]** (from TASK-01) content
    """
    learnings = []
    pattern = re.compile(
        r'-\s*\*\*\[([\w-]+)\]\*\*\s*'
        r'(?:\(from\s+([\w.-]+)\)\s+)?'
        r'(.+)',
    )
    for m in pattern.finditer(text):
        learnings.append(Learning(
            task_id=m.group(2) or "",
            category=m.group(1),
            content=m.group(3).strip(),
            change_id=change_id,
        ))
    return learnings
