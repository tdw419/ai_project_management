"""
Outcome parsing -- extract structured data from a pi agent run.

Pi's raw output is noisy. This module distills it into:
  - What happened (success / failure / partial)
  - What errors occurred
  - What files changed
  - What the agent tried (strategy)
  - How to feed this back into the next prompt
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict


class OutcomeStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"        # code changed but tests regressed
    NO_CHANGE = "no_change"    # agent didn't commit anything
    TRUST_VIOLATION = "trust_violation"
    TIMEOUT = "timeout"
    ERROR = "error"            # pi crashed or didn't run


@dataclass
class FileChange:
    path: str
    action: str  # "added", "modified", "deleted"
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class TestResult:
    passing: int = 0
    total: int = 0
    failing_tests: List[str] = field(default_factory=list)
    error_snippets: List[str] = field(default_factory=list)


@dataclass
class PiOutcome:
    """Everything we learned from one pi agent run."""
    status: OutcomeStatus = OutcomeStatus.ERROR
    exit_code: int = -1
    raw_output: str = ""

    # What changed
    file_changes: List[FileChange] = field(default_factory=list)
    commit_hash: str = ""

    # Test results
    tests_before: TestResult = field(default_factory=TestResult)
    tests_after: TestResult = field(default_factory=TestResult)

    # Errors extracted from pi's output
    errors: List[str] = field(default_factory=list)

    # Trust boundary
    trust_violations: List[str] = field(default_factory=list)

    # Strategy detection -- what did the agent try to do?
    strategy_detected: str = ""  # e.g. "created new file", "modified existing", "refactored"

    # How many attempts have been made on this task (including this one)
    attempt_number: int = 1

    @property
    def test_delta(self) -> int:
        return self.tests_after.passing - self.tests_before.passing

    @property
    def summary(self) -> str:
        """One-line summary for issue comments."""
        parts = []
        if self.status == OutcomeStatus.SUCCESS:
            delta = self.test_delta
            if delta > 0:
                parts.append(f"SUCCESS (+{delta} tests)")
            else:
                parts.append(f"SUCCESS (code landed, tests stable)")
        elif self.status == OutcomeStatus.PARTIAL:
            parts.append(f"PARTIAL (tests regressed)")
        elif self.status == OutcomeStatus.NO_CHANGE:
            parts.append("NO CHANGE")
        else:
            parts.append(f"FAILED (exit {self.exit_code})")

        parts.append(f"tests: {self.tests_before.passing} -> {self.tests_after.passing}")

        if self.file_changes:
            parts.append(f"files: {len(self.file_changes)} changed")

        if self.errors:
            parts.append(f"errors: {len(self.errors)}")

        return " | ".join(parts)

    def to_feedback_context(self) -> str:
        """Generate context string for the next retry prompt.

        This is the key output -- it turns the raw outcome into something
        the next prompt can use to avoid repeating the same mistakes.
        """
        lines = []

        lines.append(f"## Attempt #{self.attempt_number} Result: {self.status.value}")
        lines.append("")

        # Test delta
        delta = self.test_delta
        if delta > 0:
            lines.append(f"Tests improved by {delta} ({self.tests_before.passing} -> {self.tests_after.passing}).")
        elif delta < 0:
            lines.append(f"Tests REGRESSED by {abs(delta)} ({self.tests_before.passing} -> {self.tests_after.passing}).")
        else:
            lines.append(f"Tests unchanged ({self.tests_before.passing}/{self.tests_before.total}).")

        # Failing tests
        if self.tests_after.failing_tests:
            lines.append("")
            lines.append("### Still-failing tests:")
            for t in self.tests_after.failing_tests[:10]:
                lines.append(f"- {t}")

        # Errors
        if self.errors:
            lines.append("")
            lines.append("### Errors encountered:")
            for e in self.errors[:5]:
                lines.append(f"- {e}")

        # Trust violations
        if self.trust_violations:
            lines.append("")
            lines.append("### Trust boundary violations (files reverted):")
            for v in self.trust_violations:
                lines.append(f"- {v}")

        # File changes
        if self.file_changes:
            lines.append("")
            lines.append("### Files modified:")
            for fc in self.file_changes:
                lines.append(f"- [{fc.action}] {fc.path}")

        return "\n".join(lines)


def parse_outcome(
    raw_output: str,
    exit_code: int,
    file_changes: Dict[str, str],   # path -> "added"/"modified"/"deleted"
    tests_before: tuple,            # (passing, total)
    tests_after: tuple,             # (passing, total)
    trust_violations: List[str] = None,
    commit_hash_before: str = "",
    commit_hash_after: str = "",
    attempt_number: int = 1,
) -> PiOutcome:
    """Parse a pi agent run into a structured outcome."""

    outcome = PiOutcome(
        exit_code=exit_code,
        raw_output=raw_output[-4000:],  # keep last 4k
        attempt_number=attempt_number,
        trust_violations=trust_violations or [],
    )

    # -- File changes --
    outcome.file_changes = [
        FileChange(path=p, action=a)
        for p, a in file_changes.items()
    ]

    # -- Commit tracking --
    outcome.commit_hash = commit_hash_after
    code_changed = commit_hash_before != commit_hash_after

    # -- Test results --
    outcome.tests_before = TestResult(passing=tests_before[0], total=tests_before[1])
    outcome.tests_after = TestResult(passing=tests_after[0], total=tests_after[1])

    # Extract failing test names from output
    outcome.tests_after.failing_tests = _extract_failing_tests(raw_output)
    outcome.tests_after.error_snippets = _extract_error_snippets(raw_output)

    # -- Errors --
    outcome.errors = _extract_errors(raw_output)

    # -- Strategy detection --
    outcome.strategy_detected = _detect_strategy(raw_output, file_changes)

    # -- Determine status --
    has_file_changes = len(file_changes) > 0

    if trust_violations:
        outcome.status = OutcomeStatus.TRUST_VIOLATION
    elif exit_code == -1:
        outcome.status = OutcomeStatus.ERROR
    elif not code_changed and not has_file_changes:
        # Agent literally did nothing
        outcome.status = OutcomeStatus.NO_CHANGE
    elif tests_after[0] < tests_before[0]:
        # Tests regressed -- always bad regardless of code changes
        outcome.status = OutcomeStatus.PARTIAL
    elif exit_code == 0 and code_changed:
        # Code committed -- if tests didn't regress, this is progress
        # (covers both "tests increased" and "tests stable" cases)
        outcome.status = OutcomeStatus.SUCCESS
    elif exit_code == 0 and has_file_changes and not code_changed:
        # Files changed on disk but no commit (agent edited, didn't commit,
        # and auto-commit also didn't fire, e.g. non-code files only).
        # This is partial progress -- agent did work but it's not landed.
        outcome.status = OutcomeStatus.PARTIAL
    else:
        outcome.status = OutcomeStatus.FAILURE

    return outcome


# ── Extractors ──────────────────────────────────────────────────────

def _extract_failing_tests(output: str) -> List[str]:
    """Pull failing test names from test output."""
    tests = []
    patterns = [
        r'^FAIL\t(\S+)',                                     # Go: FAIL\tpkg/name
        r'^FAIL\s+\t?(\S+)',                                 # Go: FAIL   \tpkg/name (padded)
        r'FAIL:\s*(\S+)',                                    # Go: FAIL: TestName
        r'(FAILED|ERROR)\s+\[.*?\]\s+(\S+)',                 # pytest-style
        r'AssertionError.*?in\s+(test_\w+)',                 # Python unittest
        r'--- FAIL: (\S+)',                                  # Go verbose
        r'panic.*?in test (\S+)',                            # Go panic
    ]
    for pat in patterns:
        for m in re.finditer(pat, output, re.MULTILINE):
            # Pick the last group that matched
            name = m.group(m.lastindex) if m.lastindex else m.group(0)
            name = name.strip()
            if name and name not in tests and name != 'FAIL':
                tests.append(name)
    return tests[:20]


def _extract_error_snippets(output: str) -> List[str]:
    """Pull error message snippets."""
    snippets = []
    patterns = [
        r'(Error: .+?)(?:\n|$)',
        r'(FAILED .+?)(?:\n|$)',
        r'(panic: .+?)(?:\n|$)',
        r'(\w+Error: .+?)(?:\n|$)',
        r'(fatal error: .+?)(?:\n|$)',
        r'(undefined: .+?)(?:\n|$)',
        r'(cannot .+?)(?:\n|$)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, output, re.IGNORECASE):
            s = m.group(1).strip()[:200]
            if s not in snippets:
                snippets.append(s)
    return snippets[:10]


def _extract_errors(output: str) -> List[str]:
    """Extract top-level errors for feedback."""
    errors = []

    # Build errors
    build_errors = re.findall(r'(?:# |build )(\S+): (?:error|undefined|cannot)', output)
    if build_errors:
        errors.append(f"Build errors in: {', '.join(set(build_errors[:5]))}")

    # Compilation errors
    comp_errors = re.findall(r'(\S+:\d+:\d+: .*(?:error|undefined))', output)
    if comp_errors:
        for e in comp_errors[:3]:
            errors.append(e[:200])

    # Runtime errors from test output
    runtime = re.findall(r'(panic: .+)', output)
    if runtime:
        errors.append(f"Runtime panic: {runtime[0][:200]}")

    # Generic errors
    generic = re.findall(r'^(Error: .+)$', output, re.MULTILINE)
    for g in generic[:3]:
        if g not in errors:
            errors.append(g[:200])

    return errors[:10]


def _detect_strategy(output: str, file_changes: Dict[str, str]) -> str:
    """What approach did the agent try?"""
    strategies = []

    if not file_changes:
        return "no-action"

    added = sum(1 for v in file_changes.values() if v == "added")
    modified = sum(1 for v in file_changes.values() if v == "modified")
    deleted = sum(1 for v in file_changes.values() if v == "deleted")

    if added > 0:
        strategies.append(f"created {added} file{'s' if added > 1 else ''}")
    if modified > 0:
        strategies.append(f"modified {modified} file{'s' if modified > 1 else ''}")
    if deleted > 0:
        strategies.append(f"deleted {deleted} file{'s' if deleted > 1 else ''}")

    # Detect patterns from output text
    output_lower = output.lower()
    if "refactor" in output_lower:
        strategies.append("refactored")
    if "test" in output_lower and added > 0:
        strategies.append("added tests")
    if "fix" in output_lower and modified > 0:
        strategies.append("fix attempt")

    return ", ".join(strategies) if strategies else "unknown"
