"""
ASCII Experiment Runtime

A minimal runtime that executes ASCII experiment specs.
The AI writes ASCII, the runtime does the rest.

Usage:
    from ascii_runtime import ASCIIExperimentRuntime

    runtime = ASCIIExperimentRuntime(project_path=".")
    result = runtime.run_spec(ascii_content)

Or from CLI:
    python -m autospec.ascii_runtime experiment.ascii
"""

import subprocess
import time
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from .ascii_spec import (
    ASCIISpecParser,
    ASCIIResult,
    generate_history_ascii,
)
from .autoresearch.result import ExperimentResult, ExperimentStatus, ResultsLog


class ASCIIExperimentRuntime:
    """
    Minimal runtime for ASCII experiment specs.

    The runtime is FIXED - it never changes.
    The AI only writes ASCII specs.
    """

    def __init__(
        self,
        project_path: str | Path,
        results_dir: str = ".ascii_results",
    ):
        self.project_path = Path(project_path)
        self.results_dir = self.project_path / results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Results log in TSV format (for compatibility with existing AutoResearch)
        self.results_log = ResultsLog(str(self.results_dir / "results.tsv"))

        # ASCII history (for AI readability)
        self.ascii_history: list[ASCIIResult] = []

    def run_spec(
        self,
        spec_content: str,
        code_changes: Optional[dict[str, str]] = None,
    ) -> ASCIIResult:
        """
        Run an experiment from ASCII spec content.

        Args:
            spec_content: ASCII spec (any layer format)
            code_changes: Optional dict of file_path -> new_content

        Returns:
            ASCIIResult with outcome
        """
        # Parse the spec
        spec = ASCIISpecParser.parse(spec_content)

        # Record start time
        start_time = time.time()

        # Get baseline metric
        try:
            baseline_metric = self._run_eval(spec.target)
        except Exception:
            return ASCIIResult(
                spec=spec,
                metric_value=0.0,
                is_improvement=False,
                status="CRASH",
                elapsed_seconds=0.0,
            )

        # Apply code changes if provided
        if code_changes:
            for file_path, new_content in code_changes.items():
                path = self.project_path / file_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_content)

        # Run experiment with timeout
        try:
            experiment_metric = self._run_eval(
                spec.target,
                timeout=spec.budget_seconds,
            )
            status = "COMPLETE"
        except subprocess.TimeoutExpired:
            experiment_metric = baseline_metric
            status = "TIMEOUT"
        except Exception:
            experiment_metric = baseline_metric
            status = "CRASH"

        # Determine improvement
        is_improvement = spec.is_improvement(experiment_metric)

        # Record elapsed time
        elapsed = time.time() - start_time

        # Create ASCII result
        result = ASCIIResult(
            spec=spec,
            metric_value=experiment_metric,
            is_improvement=is_improvement,
            status=status,
            elapsed_seconds=elapsed,
        )

        # Log to ASCII history
        self.ascii_history.append(result)

        # Also log to TSV for compatibility
        tsv_result = ExperimentResult(
            commit_hash=self._get_commit_hash(),
            metric=experiment_metric,
            status=ExperimentStatus.KEEP if is_improvement else ExperimentStatus.DISCARD,
            description=spec.hypothesis,
            timestamp=datetime.now(),
        )
        self.results_log.append(tsv_result)

        # Revert if not improvement (keep-or-revert semantics)
        if not is_improvement and code_changes:
            self._revert_changes()

        return result

    def run_spec_file(
        self,
        spec_path: str | Path,
        code_changes: Optional[dict[str, str]] = None,
    ) -> ASCIIResult:
        """Run an experiment from an ASCII spec file."""
        spec_path = Path(spec_path)
        spec_content = spec_path.read_text()
        return self.run_spec(spec_content, code_changes)

    def _run_eval(
        self,
        target: str,
        timeout: int = 300,
        metric_pattern: Optional[str] = None,
    ) -> float:
        """
        Run the evaluation and extract metric.

        Args:
            target: Target file or command to run
            timeout: Timeout in seconds
            metric_pattern: Optional regex pattern for metric extraction

        Returns:
            Extracted metric value
        """
        original_cwd = os.getcwd()
        os.chdir(self.project_path)

        try:
            # Determine how to run the target
            if target.endswith(".py"):
                cmd = f"python {target}"
            elif target.endswith(".sh"):
                cmd = f"bash {target}"
            else:
                cmd = target  # Assume it's already a command

            # Run the command
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Combine stdout and stderr
            output = result.stdout + result.stderr

            # Extract metric
            return self._extract_metric(output, metric_pattern)

        finally:
            os.chdir(original_cwd)

    def _extract_metric(
        self,
        output: str,
        pattern: Optional[str] = None,
    ) -> float:
        """Extract a metric from command output."""
        if pattern:
            match = re.search(pattern, output)
            if match:
                return float(match.group(1))

        # Default: find first float in output
        float_pattern = r"[-+]?\d*\.\d+|\d+"
        matches = re.findall(float_pattern, output)
        if matches:
            return float(matches[0])

        raise ValueError(f"Could not extract metric from output: {output[:100]}")

    def _get_commit_hash(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_path,
            )
            return result.stdout.strip()[:7]
        except Exception:
            return "0000000"

    def _revert_changes(self) -> None:
        """Revert uncommitted changes."""
        try:
            subprocess.run(
                ["git", "checkout", "."],
                capture_output=True,
                cwd=self.project_path,
            )
        except Exception:
            pass

    def get_history_ascii(self) -> str:
        """Get ASCII visualization of experiment history."""
        return generate_history_ascii(self.ascii_history)

    def get_status_ascii(self) -> str:
        """Get current runtime status as ASCII."""
        lines = [
            "RUNTIME STATUS",
            f"Project: {self.project_path}",
            f"Experiments: {len(self.ascii_history)}",
            f"Results: {self.results_dir}",
        ]

        # Get best result
        if self.ascii_history:
            best = min(
                self.ascii_history,
                key=lambda r: r.metric_value,
            )
            lines.append(f"Best: {best.metric_value:.4f} ({best.spec.hypothesis[:30]})")

        max_width = max(len(line) for line in lines) + 2
        border = "─" * max_width

        output = [f"┌{border}┐"]
        for line in lines:
            padding = " " * (max_width - len(line) - 1)
            output.append(f"│ {line}{padding}│")
        output.append(f"└{border}┘")
        return "\n".join(output)


# CLI interface
def main():
    """CLI entry point for running ASCII specs."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m autospec.ascii_runtime <spec.ascii>")
        print("\nExample spec:")
        print('''
┌───────────────────────────────────────┐
│ H: Use AdamW optimizer                │
│ T: train.py                           │
│ M: val_bpb < 0.7                      │
│ B: 5m                                 │
└───────────────────────────────────────┘
''')
        sys.exit(1)

    spec_path = sys.argv[1]
    runtime = ASCIIExperimentRuntime(project_path=".")

    print("Running ASCII spec...")
    print(f"Loading: {spec_path}")
    print()

    result = runtime.run_spec_file(spec_path)

    print(result.to_ascii())
    print()
    print(runtime.get_history_ascii())


if __name__ == "__main__":
    main()
