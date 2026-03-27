"""
Goal State Management

Persists the top-level objective across loop iterations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class GoalState:
    """Represents the current goal and progress towards it."""

    objective: str
    success_criteria: str  # e.g., "accuracy > 0.95" or "tests_pass == True"
    current_state: str = "initialized"
    iterations: int = 0
    best_metric: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Limits
    max_iterations: int = 100
    max_time_hours: float = 24.0

    @classmethod
    def load(cls, path: Path) -> "GoalState":
        """Load goal state from YAML file with file locking."""
        import fcntl
        if not path.exists():
            raise FileNotFoundError(f"Goal file not found: {path}")

        with open(path, "r") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH)
                data = yaml.safe_load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        if not data:
            raise ValueError(f"Goal file is empty: {path}")

        return cls(
            objective=data["objective"],
            success_criteria=data["success_criteria"],
            current_state=data.get("current_state", "initialized"),
            iterations=data.get("iterations", 0),
            best_metric=data.get("best_metric"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            max_iterations=data.get("max_iterations", 100),
            max_time_hours=data.get("max_time_hours", 24.0),
        )

    def save(self, path: Path) -> None:
        """Save goal state to YAML file with file locking."""
        import fcntl
        import os
        import tempfile

        data = {
            "objective": self.objective,
            "success_criteria": self.success_criteria,
            "current_state": self.current_state,
            "iterations": self.iterations,
            "best_metric": self.best_metric,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "max_iterations": self.max_iterations,
            "max_time_hours": self.max_time_hours,
        }

        # Use temporary file for atomic write
        fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)
                    yaml.dump(data, f, default_flow_style=False)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            
            # Atomic swap
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def is_achieved(self, current_metric: float) -> bool:
        """Check if the success criteria is met."""
        # Simple parsing for common patterns
        criteria = self.success_criteria.replace(" ", "")

        if ">=" in criteria:
            _, threshold = criteria.split(">=")
            return current_metric >= float(threshold)
        elif ">" in criteria:
            _, threshold = criteria.split(">")
            return current_metric > float(threshold)
        elif "<=" in criteria:
            _, threshold = criteria.split("<=")
            return current_metric <= float(threshold)
        elif "<" in criteria:
            _, threshold = criteria.split("<")
            return current_metric < float(threshold)
        elif "==" in criteria:
            _, expected = criteria.split("==")
            return abs(current_metric - float(expected)) < 1e-9

        return False

    def is_exhausted(self) -> bool:
        """Check if we've hit our limits."""
        if self.iterations >= self.max_iterations:
            return True

        elapsed = (datetime.now() - self.created_at).total_seconds() / 3600
        if elapsed >= self.max_time_hours:
            return True

        return False

    def increment(self) -> "GoalState":
        """Return a new GoalState with iteration incremented."""
        return GoalState(
            objective=self.objective,
            success_criteria=self.success_criteria,
            current_state=self.current_state,
            iterations=self.iterations + 1,
            best_metric=self.best_metric,
            created_at=self.created_at,
            updated_at=datetime.now(),
            max_iterations=self.max_iterations,
            max_time_hours=self.max_time_hours,
        )

    def update_best(self, metric: float) -> "GoalState":
        """Return a new GoalState with updated best metric."""
        new_best = metric
        if self.best_metric is not None:
            # For "lower is better" criteria
            if "<" in self.success_criteria:
                new_best = min(self.best_metric, metric)
            else:
                new_best = max(self.best_metric, metric)

        return GoalState(
            objective=self.objective,
            success_criteria=self.success_criteria,
            current_state=self.current_state,
            iterations=self.iterations,
            best_metric=new_best,
            created_at=self.created_at,
            updated_at=datetime.now(),
            max_iterations=self.max_iterations,
            max_time_hours=self.max_time_hours,
        )
