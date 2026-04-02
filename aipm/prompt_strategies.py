"""
Prompt Strategies -- different prompt templates for different situations.

Instead of one generic prompt for every situation, we tailor the prompt
based on context:
  - Fresh task (first attempt)
  - Retry (previous attempt failed)
  - Fix regression (tests got worse)
  - Different approach (multiple failures, try something new)
  - Simplify (too many failures, scale back the task)

Each strategy takes the base prompt from the driver and enriches it
with feedback context from previous attempts.
"""

from enum import Enum
from typing import Optional

from .outcome import PiOutcome, OutcomeStatus
from .prompt_log import PromptLog


class Strategy(Enum):
    FRESH = "fresh"
    RETRY = "retry"
    FIX_REGRESSION = "fix_regression"
    DIFFERENT_APPROACH = "different_approach"
    SIMPLIFY = "simplify"
    ABANDON = "abandon"


# ── Strategy selection ─────────────────────────────────────────────

def select_strategy(
    outcome: Optional[PiOutcome],
    attempt_number: int,
    prompt_log: Optional[PromptLog] = None,
    project: str = "",
    issue_number: int = 0,
) -> Strategy:
    """Pick the right strategy based on the previous outcome.

    This is the core decision logic. It decides HOW to retry based
    on WHAT went wrong.
    """
    if outcome is None or attempt_number <= 1:
        return Strategy.FRESH

    status = outcome.status

    # Trust violation -> don't retry the same way
    if status == OutcomeStatus.TRUST_VIOLATION:
        return Strategy.DIFFERENT_APPROACH

    # Tests regressed -> fix the regression specifically
    if status == OutcomeStatus.PARTIAL:
        return Strategy.FIX_REGRESSION

    # After 3+ failures, try a completely different approach
    if attempt_number >= 4:
        return Strategy.SIMPLIFY

    # After 2+ failures, change strategy
    if attempt_number >= 3:
        return Strategy.DIFFERENT_APPROACH

    # After 1 failure, retry with error context
    if status in (OutcomeStatus.FAILURE, OutcomeStatus.NO_CHANGE):
        return Strategy.RETRY

    # Default retry
    return Strategy.RETRY


# ── Prompt enrichment ──────────────────────────────────────────────

def enrich_prompt(
    base_prompt: str,
    strategy: Strategy,
    outcome: Optional[PiOutcome],
    feedback_history: str = "",
    project: str = "",
) -> str:
    """Take a base prompt and enrich it based on strategy.

    This adds context from previous attempts to help the agent
    avoid the same mistakes.
    """
    if strategy == Strategy.FRESH:
        return base_prompt

    # Build the enrichment prefix
    prefix = _strategy_header(strategy)

    # Add feedback history (what's been tried)
    if feedback_history:
        prefix += "\n" + feedback_history + "\n"

    # Add specific guidance based on strategy
    prefix += "\n" + _strategy_guidance(strategy, outcome) + "\n"

    # Add the separator and original prompt
    prefix += "\n---\n\n### ORIGINAL TASK (with above context in mind)\n\n"

    return prefix + base_prompt


def _strategy_header(strategy: Strategy) -> str:
    """Header explaining the strategy to the agent."""
    headers = {
        Strategy.RETRY: (
            "## RETRY -- Previous Attempt Failed\n\n"
            "Your previous attempt at this task failed. Review the errors below\n"
            "and try again with a different approach.\n"
        ),
        Strategy.FIX_REGRESSION: (
            "## FIX REGRESSION -- Tests Got Worse\n\n"
            "Your previous attempt introduced test regressions. The code changes\n"
            "broke existing tests. Focus on fixing the regressions while keeping\n"
            "your new functionality.\n"
        ),
        Strategy.DIFFERENT_APPROACH: (
            "## DIFFERENT APPROACH -- Multiple Attempts Failed\n\n"
            "Multiple attempts have failed. The approach taken so far is not working.\n"
            "Consider:\n"
            "- A completely different implementation strategy\n"
            "- Breaking the task into smaller pieces\n"
            "- Looking at how similar features are implemented elsewhere in the codebase\n"
            "- Adding debug logging to understand the problem first\n"
        ),
        Strategy.SIMPLIFY: (
            "## SIMPLIFY -- Scale Back\n\n"
            "Multiple attempts have failed. Instead of the full task, implement\n"
            "the MINIMUM viable version:\n"
            "- Focus on just the core functionality\n"
            "- Skip edge cases for now\n"
            "- Use the simplest possible implementation\n"
            "- Get one test passing first, then expand\n"
        ),
        Strategy.ABANDON: (
            "## ABANDON\n\n"
            "This task has been attempted too many times. Skipping.\n"
        ),
    }
    return headers.get(strategy, "")


def _strategy_guidance(strategy: Strategy, outcome: Optional[PiOutcome]) -> str:
    """Specific guidance based on outcome + strategy."""
    if outcome is None:
        return ""

    lines = ["### Strategy Guidance\n"]

    if strategy == Strategy.RETRY:
        if outcome.errors:
            lines.append("Key errors from last attempt:")
            for e in outcome.errors[:3]:
                lines.append(f"  - `{e}`")
            lines.append("")
            lines.append("Address these errors directly. Read the relevant code before writing.")

        if outcome.strategy_detected:
            lines.append(f"Previous strategy: {outcome.strategy_detected}")
            lines.append("Try a different approach this time.")

    elif strategy == Strategy.FIX_REGRESSION:
        if outcome.tests_after.failing_tests:
            lines.append("Failing tests after your changes:")
            for t in outcome.tests_after.failing_tests[:5]:
                lines.append(f"  - `{t}`")
            lines.append("")
            lines.append("These tests passed before your changes. Fix the regression.")

        if outcome.file_changes:
            lines.append("Files you modified (regression is likely here):")
            for fc in outcome.file_changes[:5]:
                lines.append(f"  - [{fc.action}] {fc.path}")

    elif strategy == Strategy.DIFFERENT_APPROACH:
        if outcome.strategy_detected:
            lines.append(f"Previous approach ({outcome.strategy_detected}) did not work.")
        lines.append("Try a fundamentally different implementation strategy.")

    elif strategy == Strategy.SIMPLIFY:
        lines.append("Implement the absolute minimum version of this task.")
        lines.append("One test passing is better than zero. Scale back ambition.")

    return "\n".join(lines)


# ── Should we abandon? ─────────────────────────────────────────────

def should_abandon(attempt_number: int, max_attempts: int = 5) -> bool:
    """After how many attempts should we give up?"""
    return attempt_number > max_attempts
