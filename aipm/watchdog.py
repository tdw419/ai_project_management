"""
AIPM Watchdog -- monitoring, anomaly detection, and automated response.

This is the self-awareness layer. It runs periodically (via cron or inside the
loop) and does three things:

1. COLLECT metrics (rate limit, outcome rates, project health)
2. DETECT anomalies (rate limit exhaustion, stuck issues, spinning)
3. RESPOND automatically (throttle, pause, close issues, alert)

The daily log is written to ~/zion/projects/aipm/logs/YYYY-MM-DD.md.
"""

import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from .metrics import MetricsStore
from .config import CTRM_DB

# ── Data structures ──────────────────────────────────────────────────

@dataclass
class HealthCheck:
    name: str
    severity: str = "ok"       # ok, warn, critical
    message: str = ""
    action_taken: str = ""     # what we did about it (if anything)


@dataclass
class WatchdogReport:
    timestamp: str = ""
    checks: List[HealthCheck] = field(default_factory=list)
    metrics_snapshot: Dict[str, float] = field(default_factory=dict)
    actions_taken: List[str] = field(default_factory=list)

    @property
    def worst_severity(self) -> str:
        if any(c.severity == "critical" for c in self.checks):
            return "critical"
        if any(c.severity == "warn" for c in self.checks):
            return "warn"
        return "ok"


# ── Watchdog ─────────────────────────────────────────────────────────

class Watchdog:
    """
    The eyes and reflexes of the AIPM system.

    Usage:
        wd = Watchdog()
        report = wd.run_checks()
        print(report)
        # report.actions_taken lists what was automatically fixed
    """

    def __init__(self, db_path: str = None, projects_root: str = None):
        self.db_path = db_path or str(CTRM_DB)
        self.projects_root = projects_root or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "repos"
        )
        self.metrics = MetricsStore(self.db_path)
        self.log_dir = Path(self.projects_root).parent / "logs"
        self.log_dir.mkdir(exist_ok=True)

    # ── Metric collection ─────────────────────────────────────────

    def collect_metrics(self):
        """Gather current system metrics and store them."""
        now = datetime.now().isoformat()

        # 1. GitHub rate limit
        rate_info = self._get_rate_limit()
        if rate_info:
            self.metrics.put("github_graphql_remaining", rate_info["remaining"])
            self.metrics.put("github_graphql_limit", rate_info["limit"])
            pct = rate_info["remaining"] / max(rate_info["limit"], 1) * 100
            self.metrics.put("github_graphql_pct", pct)

        # 2. Outcome stats from last hour
        outcome_counts = self._get_recent_outcomes(hours=1)
        total = sum(outcome_counts.values()) or 1
        self.metrics.put("outcomes_success_rate",
                         outcome_counts.get("success", 0) / total * 100)
        self.metrics.put("outcomes_no_change_rate",
                         outcome_counts.get("no_change", 0) / total * 100)
        self.metrics.put("outcomes_total", sum(outcome_counts.values()))

        # 3. Per-project failure streaks
        for project, failures in self._get_project_failures().items():
            self.metrics.put(f"project_{project}_failures", failures,
                             tags={"project": project})

        # 4. Loop process health
        loop_pid = self._get_loop_pid()
        self.metrics.put("loop_alive", 1.0 if loop_pid else 0.0)
        if loop_pid:
            self.metrics.put("loop_pid", float(loop_pid))

        # 5. Disk usage
        try:
            usage = os.statvfs(self.projects_root)
            pct_free = usage.f_bavail / usage.f_blocks * 100
            self.metrics.put("disk_free_pct", pct_free)
        except Exception:
            pass

    # ── Health checks ─────────────────────────────────────────────

    def run_checks(self) -> WatchdogReport:
        """Run all health checks, take automated action, return report."""
        report = WatchdogReport(timestamp=datetime.now().isoformat())

        self.collect_metrics()
        report.metrics_snapshot = {
            "graphql_remaining": self.metrics.get_latest("github_graphql_remaining"),
            "success_rate": self.metrics.get_latest("outcomes_success_rate"),
            "loop_alive": self.metrics.get_latest("loop_alive"),
        }

        # Run each check
        report.checks.extend(self._check_rate_limit())
        report.checks.extend(self._check_loop_alive())
        report.checks.extend(self._check_spinning_issues())
        report.checks.extend(self._check_all_stalled())
        report.checks.extend(self._check_disk_space())
        report.checks.extend(self._check_rate_limit_trend())

        # Take automated actions for critical/warn checks
        for check in report.checks:
            action = self._respond(check)
            if action:
                report.actions_taken.append(action)

        # Write daily log entry
        self._write_log_entry(report)

        return report

    # ── Individual checks ─────────────────────────────────────────

    def _check_rate_limit(self) -> List[HealthCheck]:
        remaining = self.metrics.get_latest("github_graphql_remaining")
        if remaining is None:
            return [HealthCheck("rate_limit", "ok", "Could not check rate limit")]
        if remaining < 100:
            return [HealthCheck(
                "rate_limit", "critical",
                f"GraphQL rate limit nearly exhausted: {remaining:.0f} remaining"
            )]
        if remaining < 500:
            return [HealthCheck(
                "rate_limit", "warn",
                f"GraphQL rate limit low: {remaining:.0f} remaining"
            )]
        return [HealthCheck(
            "rate_limit", "ok",
            f"GraphQL rate limit healthy: {remaining:.0f} remaining"
        )]

    def _check_rate_limit_trend(self) -> List[HealthCheck]:
        trend = self.metrics.get_trend("github_graphql_remaining", hours=0.5)
        if trend == "falling":
            series = self.metrics.get_series("github_graphql_remaining", hours=0.5)
            if len(series) >= 3:
                # Estimate burn rate
                first_val = series[0][1]
                last_val = series[-1][1]
                elapsed = (
                    datetime.fromisoformat(series[-1][0])
                    - datetime.fromisoformat(series[0][0])
                ).total_seconds() / 3600
                if elapsed > 0:
                    burn_rate = (first_val - last_val) / elapsed
                    if burn_rate > 3000:  # more than 3000/hr is dangerous
                        return [HealthCheck(
                            "rate_limit_burn", "warn",
                            f"Burning {burn_rate:.0f} GraphQL points/hr. "
                            f"Limit will exhaust in ~{last_val / max(burn_rate, 1):.1f}h"
                        )]
        return [HealthCheck("rate_limit_burn", "ok", "Rate limit consumption sustainable")]

    def _check_loop_alive(self) -> List[HealthCheck]:
        alive = self.metrics.get_latest("loop_alive")
        if alive == 0.0 or alive is None:
            return [HealthCheck(
                "loop_process", "critical",
                "AIPM loop process is not running"
            )]
        return [HealthCheck("loop_process", "ok", "Loop running")]

    def _check_spinning_issues(self) -> List[HealthCheck]:
        """Check if the same issue has been attempted too many times recently."""
        checks = []
        with sqlite3.connect(self.db_path) as conn:
            # Find issues with 3+ attempts in the last 2 hours
            since = (datetime.now() - timedelta(hours=2)).isoformat()
            rows = conn.execute("""
                SELECT project, issue_number, COUNT(*) as attempts,
                       GROUP_CONCAT(outcome_status) as outcomes
                FROM prompt_log
                WHERE timestamp >= ?
                GROUP BY project, issue_number
                HAVING attempts >= 3
            """, (since,)).fetchall()

            for project, issue, attempts, outcomes in rows:
                # Check if all outcomes are the same (spinning)
                outcomes_list = outcomes.split(",")
                if len(set(outcomes_list)) == 1 and outcomes_list[0] in (
                    "no_change", "failure", "error"
                ):
                    checks.append(HealthCheck(
                        "spinning_issue", "warn",
                        f"{project}/#{issue} attempted {attempts}x in 2h, "
                        f"always {outcomes_list[0]}"
                    ))
        if not checks:
            checks.append(HealthCheck("spinning_issues", "ok", "No spinning issues"))
        return checks

    def _check_all_stalled(self) -> List[HealthCheck]:
        """Check if ALL active projects are showing no_change."""
        with sqlite3.connect(self.db_path) as conn:
            since = (datetime.now() - timedelta(minutes=30)).isoformat()
            rows = conn.execute("""
                SELECT project, outcome_status, COUNT(*) as cnt
                FROM prompt_log WHERE timestamp >= ?
                GROUP BY project, outcome_status
            """, (since,)).fetchall()

        if not rows:
            return [HealthCheck("stall", "ok", "No recent runs")]

        # Group by project
        projects = {}
        for project, status, cnt in rows:
            if project not in projects:
                projects[project] = {"total": 0, "success": 0}
            projects[project]["total"] += cnt
            if status == "success":
                projects[project]["success"] += cnt

        all_stalled = all(p["success"] == 0 for p in projects.values()) and len(projects) > 0
        if all_stalled:
            return [HealthCheck(
                "stall", "warn",
                f"All {len(projects)} active projects have 0 successes in last 30 min"
            )]
        return [HealthCheck("stall", "ok", "Some projects making progress")]

    def _check_disk_space(self) -> List[HealthCheck]:
        pct_free = self.metrics.get_latest("disk_free_pct")
        if pct_free is None:
            return [HealthCheck("disk", "ok", "Disk check skipped")]
        if pct_free < 5:
            return [HealthCheck("disk", "critical", f"Disk nearly full: {pct_free:.1f}% free")]
        if pct_free < 15:
            return [HealthCheck("disk", "warn", f"Disk getting low: {pct_free:.1f}% free")]
        return [HealthCheck("disk", "ok", f"Disk healthy: {pct_free:.1f}% free")]

    # ── Automated responses ───────────────────────────────────────

    def _respond(self, check: HealthCheck) -> Optional[str]:
        """Take automated action based on a health check result."""
        if check.severity == "ok":
            return None

        # Rate limit critical: pause the loop
        if check.name == "rate_limit" and check.severity == "critical":
            return self._action_throttle_loop(reason=check.message)

        # Rate limit warning: increase cycle interval
        if check.name == "rate_limit" and check.severity == "warn":
            return self._action_slow_down()

        # Rate limit burn warning: increase interval
        if check.name == "rate_limit_burn" and check.severity == "warn":
            return self._action_slow_down()

        # Loop dead: restart it
        if check.name == "loop_process" and check.severity == "critical":
            return self._action_restart_loop()

        # Spinning issue: add circuit-breaker label
        if check.name == "spinning_issue" and check.severity == "warn":
            return self._action_block_spinning_issue(check.message)

        return None

    def _action_throttle_loop(self, reason: str) -> str:
        """Kill the loop and write a pause flag."""
        pid = self._get_loop_pid()
        if pid:
            try:
                os.kill(pid, 15)  # SIGTERM
                action = f"Killed loop PID {pid} (rate limit critical)"
            except ProcessLookupError:
                action = "Loop already dead"
        else:
            action = "No loop to kill"

        # Write a throttle flag that the loop reads on startup
        flag_file = Path(self.projects_root).parent / ".aipm_throttle"
        flag_file.write_text(json.dumps({
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "action": "paused",
            "min_interval": 600,  # 10 min minimum while rate limit recovers
        }))
        return action + " + wrote throttle flag"

    def _action_slow_down(self) -> str:
        """Write a flag to increase the loop cycle interval."""
        flag_file = Path(self.projects_root).parent / ".aipm_throttle"
        flag_file.write_text(json.dumps({
            "reason": "Rate limit conservation",
            "timestamp": datetime.now().isoformat(),
            "action": "slow",
            "min_interval": 300,  # 5 min instead of 2
        }))
        return "Wrote slow-down flag (300s interval)"

    def _action_restart_loop(self) -> str:
        """Attempt to restart the loop if it's dead."""
        pid = self._get_loop_pid()
        if pid:
            return "Loop is actually alive, no restart needed"

        # Check if there's a throttle flag preventing restart
        flag_file = Path(self.projects_root).parent / ".aipm_throttle"
        if flag_file.exists():
            try:
                flag = json.loads(flag_file.read_text())
                elapsed = (
                    datetime.now() - datetime.fromisoformat(flag["timestamp"])
                ).total_seconds()
                if elapsed < 1800:  # 30 min cooldown on restart
                    return f"Throttle flag active ({elapsed:.0f}s old), not restarting"
            except Exception:
                pass

        # Restart
        try:
            main_py = Path(self.projects_root).parent / "main.py"
            log_file = "/tmp/aipm_hermes.log"
            subprocess.Popen(
                ["python3", "-u", str(main_py), "run", "120"],
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,
                cwd=str(Path(self.projects_root).parent),
                start_new_session=True,
            )
            return "Restarted AIPM loop"
        except Exception as e:
            return f"Failed to restart loop: {e}"

    def _action_block_spinning_issue(self, message: str) -> str:
        """Add circuit-breaker label to a spinning issue."""
        # Parse "project/#issue" from the message
        import re
        match = re.search(r"(\S+)/#(\d+)", message)
        if not match:
            return f"Could not parse issue from: {message}"
        project = match.group(1)
        issue = match.group(2)
        repo_path = Path(self.projects_root) / project
        if not repo_path.exists():
            return f"Repo not found: {project}"
        try:
            result = subprocess.run(
                ["gh", "issue", "edit", issue, "--add-label", "circuit-breaker"],
                cwd=repo_path, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return f"Added circuit-breaker to {project}/#{issue}"
            return f"Failed to label {project}/#{issue}: {result.stderr[:100]}"
        except Exception as e:
            return f"Error labeling issue: {e}"

    # ── Daily log ─────────────────────────────────────────────────

    def _write_log_entry(self, report: WatchdogReport):
        """Append an entry to today's daily log."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"{today}.md"

        if not log_file.exists():
            log_file.write_text(f"# AIPM Daily Log: {today}\n\n")

        ts = datetime.now().strftime("%H:%M")
        severity_icon = {"ok": "G", "warn": "W", "critical": "C"}

        lines = [f"\n## {ts} Watchdog Check\n"]
        lines.append(f"Status: **{report.worst_severity.upper()}**\n")

        if report.metrics_snapshot:
            lines.append("### Metrics")
            for name, val in report.metrics_snapshot.items():
                if val is not None:
                    lines.append(f"- {name}: {val:.0f}" if isinstance(val, float) else f"- {name}: {val}")
            lines.append("")

        if report.checks:
            lines.append("### Checks")
            for c in report.checks:
                icon = severity_icon.get(c.severity, "?")
                lines.append(f"- [{icon}] {c.name}: {c.message}")
                if c.action_taken:
                    lines.append(f"  - Action: {c.action_taken}")
            lines.append("")

        if report.actions_taken:
            lines.append("### Actions Taken")
            for a in report.actions_taken:
                lines.append(f"- {a}")
            lines.append("")

        with open(log_file, "a") as f:
            f.write("\n".join(lines))

    def generate_daily_summary(self) -> str:
        """Generate an end-of-day summary from today's log and DB."""
        today = datetime.now().strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            # Today's outcomes
            rows = conn.execute("""
                SELECT outcome_status, COUNT(*) as cnt
                FROM prompt_log
                WHERE timestamp >= ?
                GROUP BY outcome_status ORDER BY cnt DESC
            """, (today,)).fetchall()

            total = sum(r[1] for r in rows)
            outcome_lines = []
            for status, cnt in rows:
                pct = cnt / max(total, 1) * 100
                outcome_lines.append(f"  {status}: {cnt} ({pct:.0f}%)")

            # Per-project breakdown
            rows = conn.execute("""
                SELECT project, outcome_status, COUNT(*) as cnt
                FROM prompt_log
                WHERE timestamp >= ?
                GROUP BY project, outcome_status
                ORDER BY project, cnt DESC
            """, (today,)).fetchall()

            project_lines = []
            current = None
            for project, status, cnt in rows:
                if project != current:
                    current = project
                    project_lines.append(f"\n  {current}:")
                project_lines.append(f"    {status}: {cnt}")

            # Commits per project today
            commit_lines = []
            for repo_dir in Path(self.projects_root).iterdir():
                if not repo_dir.is_dir() or not (repo_dir / ".git").exists():
                    continue
                try:
                    result = subprocess.run(
                        ["git", "log", "--oneline", f"--since={today}T00:00", f"--until={today}T23:59"],
                        cwd=repo_dir, capture_output=True, text=True, timeout=5,
                    )
                    if result.stdout.strip():
                        count = len(result.stdout.strip().split("\n"))
                        commit_lines.append(f"  {repo_dir.name}: {count} commits")
                except Exception:
                    pass

        summary = f"""# AIPM Daily Summary: {today}

## Overview
- Total runs: {total}
- Outcome distribution:
{chr(10).join(outcome_lines)}

## Per-Project{"".join(project_lines)}

## Commits Today
{chr(10).join(commit_lines) if commit_lines else "  No commits recorded"}

## Generated at {datetime.now().strftime("%H:%M")}
"""
        # Append to daily log
        log_file = self.log_dir / f"{today}.md"
        with open(log_file, "a") as f:
            f.write(summary)
        return summary

    # ── Helpers ───────────────────────────────────────────────────

    def _get_rate_limit(self) -> Optional[Dict]:
        """Check GitHub GraphQL rate limit."""
        try:
            token_result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if token_result.returncode != 0:
                return None
            token = token_result.stdout.strip()

            result = subprocess.run(
                ["curl", "-s", "-H", f"Authorization: token {token}",
                 "-H", "Content-Type: application/json",
                 "-d", '{"query":"{ rateLimit { remaining limit resetAt cost } }"}',
                 "https://api.github.com/graphql"],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(result.stdout)
            if "data" in data:
                return data["data"]["rateLimit"]
        except Exception:
            pass
        return None

    def _get_recent_outcomes(self, hours: float = 1.0) -> Dict[str, int]:
        """Get outcome counts from the last N hours."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT outcome_status, COUNT(*) as cnt
                FROM prompt_log WHERE timestamp >= ?
                GROUP BY outcome_status
            """, (since,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def _get_project_failures(self) -> Dict[str, int]:
        """Get current consecutive failure count per project."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT project_id, consecutive_failures
                FROM project_state
                WHERE rowid IN (
                    SELECT MAX(rowid) FROM project_state GROUP BY project_id
                )
            """).fetchall()
        return {r[0]: r[1] for r in rows}

    def _get_loop_pid(self) -> Optional[int]:
        """Find the AIPM loop process PID."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "main.py run"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                # Return the first (oldest) PID
                pids = result.stdout.strip().split("\n")
                return int(pids[0])
        except Exception:
            pass
        return None

    def clear_throttle(self):
        """Remove the throttle flag so the loop can resume normal speed."""
        flag_file = Path(self.projects_root).parent / ".aipm_throttle"
        if flag_file.exists():
            flag_file.unlink()
            return True
        return False


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    """Run the watchdog from command line."""
    import sys

    wd = Watchdog()

    # sys.argv is ["main.py", "watchdog", "summary"] or ["-m", "aipm.watchdog", "summary"]
    subcmd = sys.argv[-1] if len(sys.argv) > 1 else ""
    if subcmd == "summary":
        print(wd.generate_daily_summary())
        return

    report = wd.run_checks()

    # Print summary
    severity_icon = {"ok": "OK", "warn": "WARN", "critical": "CRIT"}
    print(f"\nAIPM Watchdog Report -- {report.timestamp}")
    print("=" * 50)
    for c in report.checks:
        icon = severity_icon.get(c.severity, "???")
        print(f"  [{icon}] {c.name}: {c.message}")
    if report.actions_taken:
        print(f"\nActions taken:")
        for a in report.actions_taken:
            print(f"  -> {a}")
    print(f"\nOverall: {report.worst_severity.upper()}")


if __name__ == "__main__":
    main()
