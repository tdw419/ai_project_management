"""ASCII bridge - formats AIPM state as box-drawn ASCII for ascii_world viewer."""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .loop import MultiProjectLoop

from .state import ProjectState
from .priority import read_control, is_paused, get_inject_target

AIPM_ASCII_FILE = Path(
    "/home/jericho/zion/projects/ascii_world/ascii_world/data/aipm-status.ascii"
)


def format_status_ascii(loop: "MultiProjectLoop") -> str:
    """Generate ASCII status that AsciiParser renders as GUI."""
    lines = []
    lines.append(
        "╔═══════════════════════════════════════════════════════════════════════╗"
    )
    lines.append(
        "║  AIPM v2 Dashboard                                     [Neural-Reality]║"
    )
    lines.append(
        "╚═══════════════════════════════════════════════════════════════════════╝"
    )
    lines.append("")

    ctrl = read_control()
    paused = is_paused()
    inject = get_inject_target()

    if paused:
        lines.append("  ⏸  AUTONOMOUS PAUSED -- human-directed issues only")
    if inject:
        lines.append("  🚨 BYPASS MODE -- processing injected issue")
    if not paused and not inject:
        lines.append("  ▶  RUNNING normally")

    lines.append("")
    lines.append("[P] Pause  [R] Resume  [I] Inject  [S] Status")
    lines.append("")

    lines.append(
        "┌─────────────────────────────────────────────────────────────────────────┐"
    )
    lines.append(
        "│  Project Health                                                        │"
    )
    lines.append(
        "├───────────────────┬────────┬──────────┬──────────────────────────────┤"
    )
    lines.append(
        "│ Project           │ Health │ Tests    │ Queue                       │"
    )
    lines.append(
        "├───────────────────┼────────┼──────────┼──────────────────────────────┤"
    )

    for p in loop.projects:
        state = loop.state_manager.get_latest_state(p.name)
        queue = loop.queues.get(p.name)

        icon = {"green": "●", "red": "◉", "unknown": "○"}.get(
            state.health if state else "unknown", "○"
        )
        health = state.health if state else "unknown"
        tests = (
            f"{state.test_passing}/{state.test_total}"
            if state and state.test_total
            else "n/a"
        )

        if queue:
            try:
                stats = queue.stats()
                q = f"{stats['pending']}p {stats['in_progress']}a"
            except Exception:
                q = "?"
        else:
            q = "-"

        lines.append(f"│ {icon} {p.name:<16} │ {health:<7} │ {tests:<8} │ {q:<27} │")

    lines.append(
        "└───────────────────┴────────┴──────────┴──────────────────────────────┘"
    )
    lines.append("")

    for p in loop.projects:
        state = loop.state_manager.get_latest_state(p.name)
        driver = loop.drivers.get(p.name)
        gh = loop.gh_syncs.get(p.name)

        health = state.health if state else "unknown"
        color = "green" if health == "green" else "red" if health == "red" else "yellow"

        lines.append(
            f"┌─── {p.name} ({p.language}) ─────────────────────────────────────────────┐"
        )
        lines.append(
            f"│ Status: {health.upper()} | Consecutive failures: {state.consecutive_failures if state else 0}"
        )

        if state and state.commit_hash:
            lines.append(f"│ Commit: {state.commit_hash[:12]}")

        if state:
            lines.append(f"│ Tests:  {state.test_passing}/{state.test_total} passing")

        if gh and gh.is_available():
            lines.append(f"│ GitHub: {gh.repo_name}")

        if driver and driver.changes:
            for c in driver.changes:
                status_icon = {
                    "pending": "⏳",
                    "in_progress": "▶",
                    "merged": "✓",
                    "closed": "✗",
                }.get(c.status.value, "○")
                lines.append(f"│ {status_icon} {c.title[:50]}")

        lines.append(
            "└────────────────────────────────────────────────────────────────────┘"
        )
        lines.append("")

    return "\n".join(lines)


def write_ascii_status(loop: "MultiProjectLoop") -> None:
    """Write formatted ASCII status to the ascii_world data directory."""
    try:
        ascii_content = format_status_ascii(loop)
        AIPM_ASCII_FILE.write_text(ascii_content)
    except Exception as e:
        print(f"ASCII bridge error: {e}")
