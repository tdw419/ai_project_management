from dataclasses import dataclass, field
from typing import Optional, Dict
import subprocess
import time
import os
from pathlib import Path
from datetime import datetime
from .result import ExperimentResult, ExperimentStatus, ResultsLog


@dataclass
class Hypothesis:
    """A hypothesis to test in the experiment loop."""

    task_id: str
    description: str
    expected_improvement: (
        float  # Expected improvement in metric (can be positive or negative)
    )
    code_changes: Dict[str, str] = field(
        default_factory=dict
    )  # file_path -> new_content

    def apply_changes(self) -> None:
        """Apply the code changes to the filesystem."""
        for file_path, new_content in self.code_changes.items():
            path = Path(file_path)
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write the new content
            with open(path, "w") as f:
                f.write(new_content)


@dataclass
class ExperimentLoop:
    """Manages the autonomous experiment loop with keep-or-revert semantics."""

    project_path: Path
    target_file: str  # File to measure (e.g., path to test file or script)
    eval_command: str  # Command to run to get the metric
    time_budget_minutes: int = 30  # Default time budget
    lower_is_better: bool = False  # Whether lower metric values are better

    def __post_init__(self):
        self.project_path = Path(self.project_path)
        self.results_log = ResultsLog(str(self.project_path / "results.tsv"))
        self.start_time = None
        self.end_time = None

    def extract_metric(self, output: str, pattern: Optional[str] = None) -> float:
        """Extract a metric from command output.

        Args:
            output: The output string from the eval command
            pattern: Optional regex pattern to extract the metric.
                   If None, tries to extract the first float found.

        Returns:
            The extracted metric as a float

        Raises:
            ValueError: If no metric can be extracted
        """
        import re

        if pattern:
            # Use provided pattern
            match = re.search(pattern, output)
            if match:
                # Try to convert the first group to float
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    pass
        else:
            # Try to find any float in the output
            float_pattern = r"[-+]?\d*\.\d+|\d+"
            matches = re.findall(float_pattern, output)
            if matches:
                try:
                    m = float(matches[0]); print(f'DEBUG: Extracted metric {m} from output: {output}'); return m
                except ValueError:
                    pass

        raise ValueError(f"Could not extract metric from output: {output[:100]}...")

    def run_experiment(self, timeout_seconds: int = 60) -> tuple[float, str]:
        """Run the evaluation command and extract the metric.

        Args:
            timeout_seconds: Maximum time to wait for the command to complete

        Returns:
            Tuple of (metric, output)

        Raises:
            subprocess.TimeoutExpired: If the command times out
            subprocess.CalledProcessError: If the command fails
            ValueError: If no metric can be extracted from the output
        """
        # Change to project directory
        original_cwd = os.getcwd()
        os.chdir(self.project_path)

        try:
            # Run the evaluation command
            result = subprocess.run(
                self.eval_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            # Combine stdout and stderr for metric extraction
            output = result.stdout + result.stderr

            # Extract metric
            metric = self.extract_metric(output)

            return metric, output

        finally:
            # Restore original working directory
            os.chdir(original_cwd)

    def is_improvement(self, new_metric: float, baseline_metric: float) -> bool:
        """Determine if a new metric represents an improvement over the baseline.

        Args:
            new_metric: The metric from the experiment
            baseline_metric: The baseline metric to compare against

        Returns:
            True if the new metric is an improvement, False otherwise
        """
        if self.lower_is_better:
            return new_metric < baseline_metric
        else:
            return new_metric > baseline_metric

    def get_current_commit(self) -> str:
        """Get the current git commit hash.

        Returns:
            The current commit hash as a string
        """
        original_cwd = os.getcwd()
        os.chdir(self.project_path)

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            # If git is not available or we're not in a git repo, return a placeholder
            return "0000000000000000000000000000000000000000"
        finally:
            os.chdir(original_cwd)

    def commit_change(self, message: str) -> str:
        """Commit all changes with the given message.

        Args:
            message: The commit message

        Returns:
            The new commit hash
        """
        original_cwd = os.getcwd()
        os.chdir(self.project_path)

        try:
            # Add all changes
            subprocess.run(["git", "add", "."], check=True, capture_output=True)

            # Commit changes
            subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                check=True,
            )

            # Get the new commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            )
            return hash_result.stdout.strip()

        finally:
            os.chdir(original_cwd)

    def revert_last_commit(self) -> None:
        """Revert the last commit, keeping the changes in the working directory."""
        original_cwd = os.getcwd()
        os.chdir(self.project_path)

        try:
            # Reset to the previous commit, keeping changes in working directory
            subprocess.run(["git", "reset", "HEAD~1"], check=True, capture_output=True)
        finally:
            os.chdir(original_cwd)

    def run(self, hypothesis: Hypothesis) -> ExperimentResult:
        """Run a single experiment with the given hypothesis.

        Args:
            hypothesis: The hypothesis to test

        Returns:
            An ExperimentResult representing the outcome of the experiment
        """
        # Record start time if this is the first experiment
        if self.start_time is None:
            self.start_time = time.time()

        # Get baseline commit first (so we have it even if metric collection fails)
        try:
            baseline_commit = self.get_current_commit()
        except Exception as e:
            # If we can't get the current commit, we can't properly track the experiment
            return ExperimentResult(
                commit_hash="0000000000000000000000000000000000000000",
                metric=0.0,
                status=ExperimentStatus.CRASH,
                description=f"Failed to get current commit: {str(e)}",
                timestamp=datetime.now(),
            )

        # Get baseline metric (current state) - if this fails, we continue with a default value
        try:
            baseline_metric, baseline_output = self.run_experiment()
        except Exception:
            # If we can't get a baseline metric, we continue with a default value of 0.0
            # but we still have the baseline commit for tracking
            baseline_metric = 0.0

        # Initialize variables for the experiment
        experiment_commit = baseline_commit
        experiment_metric = 0.0
        status = ExperimentStatus.CRASH  # Default status
        description = f"{hypothesis.description} - Experiment failed"

        # Apply the hypothesis changes
        hypothesis.apply_changes()

        try:
            # Try to commit the changes
            commit_message = f"Experiment: {hypothesis.description}"
            experiment_commit = self.commit_change(commit_message)

            # Run the experiment
            experiment_metric, experiment_output = self.run_experiment()

            # Determine if it's an improvement
            if self.is_improvement(experiment_metric, baseline_metric):
                status = ExperimentStatus.KEEP
                description = f"{hypothesis.description} - Improved metric from {baseline_metric:.4f} to {experiment_metric:.4f}"
            else:
                status = ExperimentStatus.DISCARD
                description = f"{hypothesis.description} - No improvement: {baseline_metric:.4f} -> {experiment_metric:.4f}"
                # Revert the change since it didn't improve
                self.revert_last_commit()

        except subprocess.TimeoutExpired:
            status = ExperimentStatus.CRASH
            description = f"{hypothesis.description} - Experiment timed out"
            experiment_metric = 0.0
            experiment_commit = baseline_commit  # Reverted to baseline
            # Revert changes on timeout
            self.revert_last_commit()

        except Exception as e:
            status = ExperimentStatus.CRASH
            description = f"{hypothesis.description} - Experiment failed: {str(e)}"
            experiment_metric = 0.0
            experiment_commit = baseline_commit  # Reverted to baseline
            # Revert changes on failure
            self.revert_last_commit()

        # Create and return the result
        result = ExperimentResult(
            commit_hash=experiment_commit,
            metric=experiment_metric,
            status=status,
            description=description,
            timestamp=datetime.now(),
        )

        # Log the result
        self.results_log.append(result)

        # Check if we've exceeded our time budget
        if self.start_time and (time.time() - self.start_time) > (
            self.time_budget_minutes * 60
        ):
            self.end_time = time.time()

        return result
