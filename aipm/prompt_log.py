"""
Prompt Log -- track every prompt sent to pi and its outcome.

This is the memory of what worked and what didn't. Over time:
  - You can see which prompt patterns succeed
  - You can avoid repeating failed strategies
  - You can generate smarter retry prompts with full history

Storage: SQLite table `prompt_log` in the same DB as runtime state.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass

from .outcome import PiOutcome, OutcomeStatus


@dataclass
class PromptRecord:
    """One prompt -> one outcome."""
    id: int = 0
    project: str = ""
    issue_number: int = 0
    timestamp: str = ""

    # The prompt
    prompt_text: str = ""
    prompt_strategy: str = ""    # "fresh", "retry", "fix_regression", "abandon"
    prompt_version: int = 1

    # The outcome
    outcome_status: str = ""     # OutcomeStatus.value
    exit_code: int = -1
    test_delta: int = 0
    files_changed: int = 0
    errors_json: str = "[]"
    strategy_detected: str = ""

    # Feedback context (for generating next prompt)
    feedback_context: str = ""

    # Attempt tracking
    attempt_number: int = 1

    # Provider tracking (for model routing)
    provider: str = ""  # "local" or "cloud"

    # Grounded state snapshots (before/after)
    state_before_json: str = ""  # {"commit":"abc","tests":"10/10","test_output":"..."}
    state_after_json: str = ""
    diff_summary: str = ""       # git diff --stat output


class PromptLog:
    """Store and query prompt/outcome pairs."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    prompt_strategy TEXT DEFAULT 'fresh',
                    prompt_version INTEGER DEFAULT 1,
                    outcome_status TEXT DEFAULT '',
                    exit_code INTEGER DEFAULT -1,
                    test_delta INTEGER DEFAULT 0,
                    files_changed INTEGER DEFAULT 0,
                    errors_json TEXT DEFAULT '[]',
                    strategy_detected TEXT DEFAULT '',
                    feedback_context TEXT DEFAULT '',
                    attempt_number INTEGER DEFAULT 1,
                    state_before_json TEXT DEFAULT '',
                    state_after_json TEXT DEFAULT '',
                    diff_summary TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_log_project ON prompt_log(project)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_log_issue ON prompt_log(issue_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_log_status ON prompt_log(outcome_status)")
            # Add columns if they don't exist (migration for existing DBs)
            try:
                conn.execute("ALTER TABLE prompt_log ADD COLUMN state_before_json TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE prompt_log ADD COLUMN state_after_json TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE prompt_log ADD COLUMN diff_summary TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE prompt_log ADD COLUMN provider TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            # Create index on provider AFTER column migration
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_log_provider ON prompt_log(provider)")

    def record(
        self,
        project: str,
        issue_number: int,
        prompt_text: str,
        outcome: PiOutcome,
        prompt_strategy: str = "fresh",
        prompt_version: int = 1,
        state_before: dict = None,
        state_after: dict = None,
        diff_summary: str = "",
        provider: str = "",
    ) -> int:
        """Record a prompt + outcome pair. Returns the record ID."""
        feedback = outcome.to_feedback_context()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO prompt_log (
                    project, issue_number, timestamp,
                    prompt_text, prompt_strategy, prompt_version,
                    outcome_status, exit_code, test_delta,
                    files_changed, errors_json, strategy_detected,
                    feedback_context, attempt_number,
                    state_before_json, state_after_json, diff_summary,
                    provider
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project, issue_number, datetime.now().isoformat(),
                prompt_text, prompt_strategy, prompt_version,
                outcome.status.value, outcome.exit_code, outcome.test_delta,
                len(outcome.file_changes),
                json.dumps(outcome.errors),
                outcome.strategy_detected,
                feedback, outcome.attempt_number,
                json.dumps(state_before) if state_before else "",
                json.dumps(state_after) if state_after else "",
                diff_summary,
                provider,
            ))
            return cursor.lastrowid

    def get_attempts(self, project: str, issue_number: int) -> List[PromptRecord]:
        """Get all attempts for a specific issue."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM prompt_log
                WHERE project = ? AND issue_number = ?
                ORDER BY attempt_number ASC
            """, (project, issue_number))
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def get_latest_attempt(self, project: str, issue_number: int) -> Optional[PromptRecord]:
        """Get the most recent attempt for an issue."""
        attempts = self.get_attempts(project, issue_number)
        return attempts[-1] if attempts else None

    def get_feedback_history(self, project: str, issue_number: int) -> str:
        """Get the full feedback history for an issue as a context string.

        This is what gets injected into retry prompts so the agent
        knows what's already been tried. Includes grounded state snapshots.
        """
        attempts = self.get_attempts(project, issue_number)
        if not attempts:
            return ""

        lines = [f"### Previous Attempts ({len(attempts)} total)\n"]

        for rec in attempts:
            lines.append(f"#### Attempt #{rec.attempt_number} [{rec.prompt_strategy}]")
            lines.append(f"Outcome: {rec.outcome_status}")
            lines.append(f"Test delta: {rec.test_delta:+d}")
            if rec.files_changed:
                lines.append(f"Files changed: {rec.files_changed}")
            if rec.strategy_detected:
                lines.append(f"Strategy: {rec.strategy_detected}")
            errors = json.loads(rec.errors_json) if rec.errors_json else []
            if errors:
                lines.append("Errors:")
                for e in errors[:3]:
                    lines.append(f"  - {e}")

            # Grounded state snapshot
            if rec.state_before_json and rec.state_after_json:
                try:
                    before = json.loads(rec.state_before_json)
                    after = json.loads(rec.state_after_json)
                    lines.append(f"State: {before.get('tests','?')} -> {after.get('tests','?')} "
                               f"(commit {before.get('commit','?')[:8]} -> {after.get('commit','?')[:8]})")
                except (json.JSONDecodeError, TypeError):
                    pass

            if rec.diff_summary:
                lines.append(f"Diff:\n{rec.diff_summary[:500]}")

            lines.append("")

        # Add latest feedback context
        latest = attempts[-1]
        if latest.feedback_context:
            lines.append(latest.feedback_context)

        return "\n".join(lines)

    # ── Analytics ────────────────────────────────────────────────

    def success_rate(self, project: str, strategy: str = None) -> float:
        """Success rate for a project (optionally filtered by strategy)."""
        with sqlite3.connect(self.db_path) as conn:
            if strategy:
                total = conn.execute(
                    "SELECT COUNT(*) FROM prompt_log WHERE project = ? AND prompt_strategy = ?",
                    (project, strategy)
                ).fetchone()[0]
                successes = conn.execute(
                    "SELECT COUNT(*) FROM prompt_log WHERE project = ? AND prompt_strategy = ? AND outcome_status = 'success'",
                    (project, strategy)
                ).fetchone()[0]
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM prompt_log WHERE project = ?",
                    (project,)
                ).fetchone()[0]
                successes = conn.execute(
                    "SELECT COUNT(*) FROM prompt_log WHERE project = ? AND outcome_status = 'success'",
                    (project,)
                ).fetchone()[0]

        return successes / total if total > 0 else 0.0

    def strategy_stats(self, project: str) -> Dict[str, Dict]:
        """Stats per prompt strategy for a project."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT prompt_strategy,
                       COUNT(*) as total,
                       SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
                       AVG(test_delta) as avg_delta,
                       AVG(files_changed) as avg_files
                FROM prompt_log
                WHERE project = ?
                GROUP BY prompt_strategy
            """, (project,))

            stats = {}
            for row in cursor.fetchall():
                strategy, total, successes, avg_delta, avg_files = row
                stats[strategy] = {
                    "total": total,
                    "successes": successes,
                    "rate": successes / total if total > 0 else 0.0,
                    "avg_test_delta": round(avg_delta or 0, 1),
                    "avg_files_changed": round(avg_files or 0, 1),
                }
            return stats

    def recent_errors(self, project: str, limit: int = 10) -> List[str]:
        """Get recent error patterns for a project."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT errors_json FROM prompt_log
                WHERE project = ? AND outcome_status != 'success'
                ORDER BY timestamp DESC LIMIT ?
            """, (project, limit))

            all_errors = []
            for row in cursor.fetchall():
                errors = json.loads(row[0])
                all_errors.extend(errors)

        # Deduplicate and return top errors
        seen = set()
        unique = []
        for e in all_errors:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        return unique[:10]

    def cross_issue_context(self, project: str, current_issue: int, limit: int = 5) -> str:
        """Get relevant context from OTHER issues in the same project.

        Finds failures from other issues that might be related (shared errors,
        shared files, shared dependencies). Returns a context string to inject
        into the current issue's prompt.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Get recent failures from OTHER issues
            cursor = conn.execute("""
                SELECT issue_number, errors_json, strategy_detected,
                       outcome_status, test_delta, files_changed,
                       diff_summary
                FROM prompt_log
                WHERE project = ? AND issue_number != ? AND outcome_status != 'success'
                ORDER BY timestamp DESC LIMIT ?
            """, (project, current_issue, limit))

            rows = cursor.fetchall()

        if not rows:
            return ""

        lines = ["### Cross-Issue Learning (failures from other tasks)\n"]

        for row in rows:
            lines.append(f"- Issue #{row['issue_number']} [{row['outcome_status']}]: "
                        f"delta={row['test_delta']}, strategy={row['strategy_detected']}")
            errors = json.loads(row["errors_json"]) if row["errors_json"] else []
            if errors:
                for e in errors[:2]:
                    lines.append(f"  - {e[:100]}")

        # Also pull common error patterns
        common = self._common_error_patterns(project)
        if common:
            lines.append("\n### Common error patterns in this project:")
            for pattern, count in common[:5]:
                lines.append(f"  - ({count}x) {pattern[:120]}")

        return "\n".join(lines)

    def _common_error_patterns(self, project: str) -> List[tuple]:
        """Find error patterns that recur across issues."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT errors_json FROM prompt_log
                WHERE project = ? AND outcome_status != 'success'
                ORDER BY timestamp DESC LIMIT 20
            """, (project,))

            error_counts: Dict[str, int] = {}
            for row in cursor.fetchall():
                errors = json.loads(row[0]) if row[0] else []
                for e in errors:
                    # Normalize: take first 80 chars as pattern
                    pattern = e[:80].strip()
                    error_counts[pattern] = error_counts.get(pattern, 0) + 1

        # Sort by frequency
        return sorted(error_counts.items(), key=lambda x: -x[1])

    def _row_to_record(self, row) -> PromptRecord:
        return PromptRecord(
            id=row["id"],
            project=row["project"],
            issue_number=row["issue_number"],
            timestamp=row["timestamp"],
            prompt_text=row["prompt_text"],
            prompt_strategy=row["prompt_strategy"],
            prompt_version=row["prompt_version"],
            outcome_status=row["outcome_status"],
            exit_code=row["exit_code"],
            test_delta=row["test_delta"],
            files_changed=row["files_changed"],
            errors_json=row["errors_json"],
            strategy_detected=row["strategy_detected"],
            feedback_context=row["feedback_context"],
            attempt_number=row["attempt_number"],
            state_before_json=row["state_before_json"] if "state_before_json" in row.keys() else "",
            state_after_json=row["state_after_json"] if "state_after_json" in row.keys() else "",
            diff_summary=row["diff_summary"] if "diff_summary" in row.keys() else "",
            provider=row["provider"] if "provider" in row.keys() else "",
        )
