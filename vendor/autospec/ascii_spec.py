"""
ASCII Experiment Spec Parser

Parses ASCII experiment specs that AIs naturally output.
The spec IS the program - no Python code needed from the AI.

Layer 0 (minimal):
    H: Use AdamW optimizer
    T: train.py
    M: val_bpb < 0.7
    B: 5m

Layer 1 (boxed):
    ┌───────────────────────────┐
    │ H: Use AdamW optimizer    │
    │ T: train.py               │
    │ M: val_bpb < 0.7          │
    │ B: 5m                     │
    └───────────────────────────┘

Layer 2 (with ID):
    ╔═══════════════════════════╗
    ║ EXPERIMENT: optimizer-001 ║
    ╠═══════════════════════════╣
    ║ H: Use AdamW optimizer    ║
    ║ T: train.py               ║
    ║ M: val_bpb < 0.7          ║
    ║ B: 5m                     │
    ╚═══════════════════════════╝
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re
from datetime import datetime


@dataclass
class ASCIIExperimentSpec:
    """An experiment spec parsed from ASCII format."""

    hypothesis: str  # H: What we're testing
    target: str  # T: File to modify/run
    metric: str  # M: Metric condition (e.g., "val_bpb < 0.7")
    budget: str  # B: Time budget (e.g., "5m", "30s", "1h")
    experiment_id: Optional[str] = None  # Optional ID from Layer 2+

    # Parsed metric details
    metric_name: str = field(default="", init=False)
    metric_operator: str = field(default="", init=False)
    metric_threshold: float = field(default=0.0, init=False)

    # Parsed budget in seconds
    budget_seconds: int = field(default=300, init=False)

    def __post_init__(self):
        self._parse_metric()
        self._parse_budget()

    def _parse_metric(self) -> None:
        """Parse metric string into name, operator, threshold."""
        # Pattern: metric_name operator value
        # Examples: "val_bpb < 0.7", "accuracy > 0.9", "loss <= 0.5"
        pattern = r"([\w_]+)\s*(<=?|>=?|==?)\s*([\d.]+)"
        match = re.search(pattern, self.metric)
        if match:
            self.metric_name = match.group(1)
            self.metric_operator = match.group(2)
            self.metric_threshold = float(match.group(3))
        else:
            # Default: just extract the metric name
            self.metric_name = self.metric.split()[0] if self.metric else ""

    def _parse_budget(self) -> None:
        """Parse budget string into seconds."""
        # Examples: "5m", "30s", "1h", "90"
        pattern = r"(\d+)\s*([smh]?)"
        match = re.match(pattern, self.budget.strip())
        if match:
            value = int(match.group(1))
            unit = match.group(2) or "s"  # Default to seconds

            if unit == "s":
                self.budget_seconds = value
            elif unit == "m":
                self.budget_seconds = value * 60
            elif unit == "h":
                self.budget_seconds = value * 3600
            else:
                self.budget_seconds = value

    def is_improvement(self, value: float) -> bool:
        """Check if a metric value meets the threshold."""
        if not self.metric_operator:
            return True

        if self.metric_operator == "<":
            return value < self.metric_threshold
        elif self.metric_operator == "<=":
            return value <= self.metric_threshold
        elif self.metric_operator == ">":
            return value > self.metric_threshold
        elif self.metric_operator == ">=":
            return value >= self.metric_threshold
        elif self.metric_operator == "==":
            return value == self.metric_threshold
        return True

    def to_ascii(self, layer: int = 1) -> str:
        """Convert spec back to ASCII format."""
        if layer == 0:
            # Minimal format
            return f"""H: {self.hypothesis}
T: {self.target}
M: {self.metric}
B: {self.budget}"""

        elif layer == 1:
            # Boxed format
            lines = [
                f"H: {self.hypothesis}",
                f"T: {self.target}",
                f"M: {self.metric}",
                f"B: {self.budget}",
            ]
            max_width = max(len(line) for line in lines) + 2
            border = "─" * max_width

            output = [f"┌{border}┐"]
            for line in lines:
                padding = " " * (max_width - len(line) - 1)
                output.append(f"│ {line}{padding}│")
            output.append(f"└{border}┘")
            return "\n".join(output)

        elif layer == 2:
            # Full format with ID
            lines = [
                f"H: {self.hypothesis}",
                f"T: {self.target}",
                f"M: {self.metric}",
                f"B: {self.budget}",
            ]
            max_width = max(len(line) for line in lines) + 2
            id_line = f"EXPERIMENT: {self.experiment_id or 'unnamed'}"
            max_width = max(max_width, len(id_line) + 2)
            border = "═" * max_width

            output = [f"╔{border}╗"]
            padding = " " * (max_width - len(id_line) - 1)
            output.append(f"║ {id_line}{padding}║")
            output.append(f"╠{border}╣")
            for line in lines:
                padding = " " * (max_width - len(line) - 1)
                output.append(f"║ {line}{padding}║")
            output.append(f"╚{border}╝")
            return "\n".join(output)

        return self.to_ascii(0)


class ASCIISpecParser:
    """Parser for ASCII experiment specs."""

    # Regex patterns for parsing
    KEY_PATTERN = r"([HTMB]):\s*(.+)"
    ID_PATTERN = r"EXPERIMENT:\s*(\S+)"

    @classmethod
    def parse(cls, content: str) -> ASCIIExperimentSpec:
        """Parse an ASCII spec from string content.

        Args:
            content: ASCII spec content (any layer format)

        Returns:
            Parsed ASCIIExperimentSpec

        Raises:
            ValueError: If required fields (H, T, M, B) are missing
        """
        fields = {"H": None, "T": None, "M": None, "B": None}
        experiment_id = None

        # Strip box characters and extract key-value pairs
        for line in content.split("\n"):
            line = line.strip()

            # Skip empty lines and box drawing characters
            if not line or all(c in "┌┐└┘├┤┬┴┼─│╔╗╚╝╠╣╦╩╬═║" for c in line):
                continue

            # Try to extract experiment ID
            id_match = re.search(cls.ID_PATTERN, line)
            if id_match:
                experiment_id = id_match.group(1)
                continue

            # Try to extract H/T/M/B fields
            kv_match = re.search(cls.KEY_PATTERN, line)
            if kv_match:
                key = kv_match.group(1)
                # Strip trailing box characters and whitespace
                value = kv_match.group(2).strip()
                # Remove trailing box characters (│, ║)
                value = value.rstrip("│║ ").strip()
                if key in fields:
                    fields[key] = value

        # Validate required fields
        missing = [k for k, v in fields.items() if v is None]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        return ASCIIExperimentSpec(
            hypothesis=fields["H"],
            target=fields["T"],
            metric=fields["M"],
            budget=fields["B"],
            experiment_id=experiment_id,
        )

    @classmethod
    def parse_file(cls, path: Path | str) -> ASCIIExperimentSpec:
        """Parse an ASCII spec from a file.

        Args:
            path: Path to the ASCII spec file

        Returns:
            Parsed ASCIIExperimentSpec
        """
        path = Path(path)
        content = path.read_text()
        return cls.parse(content)


@dataclass
class ASCIIResult:
    """Result of running an ASCII experiment, formatted as ASCII."""

    spec: ASCIIExperimentSpec
    metric_value: float
    is_improvement: bool
    status: str  # "KEEP", "REVERT", "CRASH", "RUNNING"
    elapsed_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_ascii(self) -> str:
        """Format result as ASCII box."""
        status_icon = "✓" if self.is_improvement else "✗"
        status_color = "KEEP" if self.is_improvement else "REVERT"

        lines = [
            f"RESULT: {self.spec.experiment_id or 'experiment'}",
            f"STATUS: {self.status} {status_icon}",
            f"METRIC: {self.spec.metric_name}={self.metric_value:.4f}",
            f"TARGET: {self.spec.metric} → {status_color}",
            f"ELAPSED: {self.elapsed_seconds:.1f}s",
        ]

        max_width = max(len(line) for line in lines) + 2
        border = "═" * max_width

        output = [f"╔{border}╗"]
        for line in lines:
            padding = " " * (max_width - len(line) - 1)
            output.append(f"║ {line}{padding}║")
        output.append(f"╚{border}╝")
        return "\n".join(output)


def generate_history_ascii(results: list[ASCIIResult]) -> str:
    """Generate ASCII visualization of experiment history."""
    if not results:
        return "No experiments yet."

    # Extract metrics for visualization
    metrics = [(r.spec.experiment_id or str(i), r.metric_value, r.is_improvement)
               for i, r in enumerate(results)]

    min_val = min(m[1] for m in metrics)
    max_val = max(m[1] for m in metrics)
    range_val = max_val - min_val if max_val != min_val else 1.0

    # Build ASCII chart (10 rows)
    chart_height = 6
    chart_lines = [""] * chart_height

    for i, (name, value, improved) in enumerate(metrics):
        # Normalize value to chart position
        normalized = (value - min_val) / range_val
        row = int((1 - normalized) * (chart_height - 1))
        row = max(0, min(chart_height - 1, row))

        # Build column
        for r in range(chart_height):
            if r == row:
                chart_lines[r] += " ●"
            else:
                chart_lines[r] += "  "

    # Add Y-axis labels
    y_labels = []
    for r in range(chart_height):
        val = max_val - (r / (chart_height - 1)) * range_val
        y_labels.append(f"{val:.2f} ┤")

    # Combine labels and chart
    chart = "METRIC HISTORY:\n"
    for label, line in zip(y_labels, chart_lines):
        chart += f"{label}{line}\n"

    # Add X-axis
    chart += "      └" + "─" * len(metrics) * 2 + "\n"

    # Add legend
    chart += "\nLEGEND:\n"
    for i, (name, value, improved) in enumerate(metrics):
        icon = "✓" if improved else "✗"
        chart += f"  {i+1}. {name}: {value:.4f} {icon}\n"

    return chart
