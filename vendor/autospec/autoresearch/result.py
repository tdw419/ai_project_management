from enum import Enum
from datetime import datetime
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    """Status of an experiment."""

    KEEP = "keep"
    DISCARD = "discard"
    CRASH = "crash"
    PENDING = "pending"


class ExperimentResult(BaseModel):
    """Result of an experiment."""

    commit_hash: str = Field(..., description="Git commit hash for this experiment")
    metric: float = Field(
        ...,
        description="Metric value for this experiment (higher is better unless specified otherwise)",
    )
    status: ExperimentStatus = Field(..., description="Status of the experiment")
    description: str = Field(
        ..., description="Description of what was changed in this experiment"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the experiment was run"
    )

    def to_tsv(self) -> str:
        """Convert the result to a TSV (tab-separated values) line.

        Returns:
            A string representing the result in TSV format with header:
            commit_hash\tmetric\tstatus\tdescription\ttimestamp
        """
        # Format timestamp as ISO string for consistency
        timestamp_str = self.timestamp.isoformat()
        return f"{self.commit_hash}\t{self.metric}\t{self.status.value}\t{self.description}\t{timestamp_str}"


class ResultsLog:
    """Manages a log of experiment results in TSV format."""

    HEADER = "commit_hash\tmetric\tstatus\tdescription\ttimestamp"

    def __init__(self, log_path: str):
        self.log_path = log_path
        # Ensure the directory exists
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)

        # Create the file with header if it doesn't exist
        if not Path(log_path).exists():
            with open(log_path, "w") as f:
                f.write(self.HEADER + "\n")

    def append(self, result: ExperimentResult) -> None:
        """Append a result to the log.

        Args:
            result: The ExperimentResult to append
        """
        with open(self.log_path, "a") as f:
            f.write(result.to_tsv() + "\n")

    def read_all(self) -> list[ExperimentResult]:
        """Read all results from the log.

        Returns:
            List of ExperimentResult objects, sorted by timestamp (oldest first)
        """
        results = []
        with open(self.log_path, "r") as f:
            lines = f.readlines()

        # Skip header
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) != 5:
                continue  # Skip malformed lines

            commit_hash, metric_str, status_str, description, timestamp_str = parts
            try:
                result = ExperimentResult(
                    commit_hash=commit_hash,
                    metric=float(metric_str),
                    status=ExperimentStatus(status_str),
                    description=description,
                    timestamp=datetime.fromisoformat(timestamp_str),
                )
                results.append(result)
            except (ValueError, KeyError):
                # Skip lines that can't be parsed
                continue

        # Sort by timestamp (oldest first)
        results.sort(key=lambda r: r.timestamp)
        return results

    def get_best(self, lower_is_better: bool = False) -> Optional[ExperimentResult]:
        """Get the best result based on metric value.

        Args:
            lower_is_better: If True, lower metric values are better.
                            If False (default), higher metric values are better.

        Returns:
            The best ExperimentResult, or None if no results exist
        """
        results = self.read_all()
        if not results:
            return None

        if lower_is_better:
            return min(results, key=lambda r: r.metric)
        else:
            return max(results, key=lambda r: r.metric)

    def get_last(self) -> Optional[ExperimentResult]:
        """Get the most recent result.

        Returns:
            The most recent ExperimentResult, or None if no results exist
        """
        results = self.read_all()
        if not results:
            return None

        # Return the last result (most recent since we sorted by timestamp ascending)
        return results[-1]
