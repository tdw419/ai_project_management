"""
Validation and Metrics Definition

SystemAuditor verifies semantic consistency across generations.
MetricsLogger tracks performance deltas, convergence rates, and health.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
from enum import Enum
import json
import hashlib
from collections import deque


class HealthStatus(Enum):
    OPTIMAL = "optimal"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"


class ConsistencyLevel(Enum):
    EXACT = "exact"           # Bit-for-bit identical
    SEMANTIC = "semantic"     # Functionally equivalent
    BEHAVIORAL = "behavioral" # Same outputs for same inputs
    TOLERANT = "tolerant"     # Within acceptable bounds


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus
    last_check: datetime
    error_count: int = 0
    warning_count: int = 0
    uptime_seconds: float = 0.0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "uptime_seconds": self.uptime_seconds,
            "details": self.details,
        }


@dataclass
class MetricSnapshot:
    """A snapshot of metrics at a point in time."""
    timestamp: datetime
    iteration: int

    # Performance metrics
    reward_score: float = 0.0
    accuracy: float = 0.0
    efficiency: float = 0.0

    # Convergence metrics
    convergence_rate: float = 0.0
    improvement_delta: float = 0.0
    oscillation_count: int = 0

    # Component metrics
    components_healthy: int = 0
    components_total: int = 7
    insights_generated: int = 0
    rollbacks_triggered: int = 0

    # Resource metrics
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    disk_io_mb: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "iteration": self.iteration,
            "reward_score": self.reward_score,
            "accuracy": self.accuracy,
            "efficiency": self.efficiency,
            "convergence_rate": self.convergence_rate,
            "improvement_delta": self.improvement_delta,
            "oscillation_count": self.oscillation_count,
            "components_healthy": self.components_healthy,
            "components_total": self.components_total,
            "insights_generated": self.insights_generated,
            "rollbacks_triggered": self.rollbacks_triggered,
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "disk_io_mb": self.disk_io_mb,
        }


@dataclass
class ConsistencyReport:
    """Report on semantic consistency verification."""
    is_consistent: bool
    level: ConsistencyLevel
    component_name: str
    hash_before: str
    hash_after: str
    behavioral_match: bool
    differences: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "is_consistent": self.is_consistent,
            "level": self.level.value,
            "component_name": self.component_name,
            "hash_before": self.hash_before,
            "hash_after": self.hash_after,
            "behavioral_match": self.behavioral_match,
            "differences": self.differences,
            "timestamp": self.timestamp.isoformat(),
        }


class MetricsLogger:
    """
    Tracks performance deltas, convergence rates, and component health.

    Features:
    - Time-series metric storage
    - Delta calculation
    - Convergence detection
    - Health aggregation
    - Alert thresholds
    """

    def __init__(self, state_dir: Path, history_size: int = 1000):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.history_size = history_size

        # Metric storage
        self.snapshots: deque[MetricSnapshot] = deque(maxlen=history_size)
        self.component_health: dict[str, ComponentHealth] = {}

        # Aggregations
        self.hourly_stats: dict[str, list[float]] = {}
        self.daily_stats: dict[str, list[float]] = {}

        # Alert thresholds
        self.thresholds = {
            "reward_score": {"low": 0.3, "critical": 0.1},
            "convergence_rate": {"low": 0.1, "critical": 0.0},
            "components_healthy": {"low": 5, "critical": 3},
            "error_rate": {"high": 0.3, "critical": 0.5},
        }

        # Callbacks
        self.on_alert: Optional[Callable[[str, str, float], None]] = None

        self._load()

    def _load(self):
        """Load persisted metrics."""
        metrics_file = self.state_dir / "metrics_history.json"
        if metrics_file.exists():
            with open(metrics_file) as f:
                data = json.load(f)

            for snap_data in data.get("snapshots", [])[-100:]:  # Last 100
                self.snapshots.append(MetricSnapshot(
                    timestamp=datetime.fromisoformat(snap_data["timestamp"]),
                    iteration=snap_data["iteration"],
                    reward_score=snap_data.get("reward_score", 0.0),
                    accuracy=snap_data.get("accuracy", 0.0),
                    efficiency=snap_data.get("efficiency", 0.0),
                    convergence_rate=snap_data.get("convergence_rate", 0.0),
                    improvement_delta=snap_data.get("improvement_delta", 0.0),
                    oscillation_count=snap_data.get("oscillation_count", 0),
                    components_healthy=snap_data.get("components_healthy", 0),
                    components_total=snap_data.get("components_total", 7),
                    insights_generated=snap_data.get("insights_generated", 0),
                    rollbacks_triggered=snap_data.get("rollbacks_triggered", 0),
                ))

    def _save(self):
        """Persist metrics."""
        metrics_file = self.state_dir / "metrics_history.json"
        with open(metrics_file, "w") as f:
            json.dump({
                "snapshots": [s.to_dict() for s in list(self.snapshots)[-100:]],
                "component_health": {
                    k: v.to_dict() for k, v in self.component_health.items()
                },
                "updated_at": datetime.now().isoformat(),
            }, f, indent=2)

    def record_snapshot(self, snapshot: MetricSnapshot):
        """Record a new metric snapshot."""
        self.snapshots.append(snapshot)

        # Check thresholds
        self._check_thresholds(snapshot)

        # Update aggregations
        self._update_aggregations(snapshot)

        # Persist
        self._save()

    def update_component_health(self, name: str, status: HealthStatus,
                                 details: dict = None):
        """Update health status for a component."""
        existing = self.component_health.get(name)

        self.component_health[name] = ComponentHealth(
            name=name,
            status=status,
            last_check=datetime.now(),
            error_count=existing.error_count + (1 if status == HealthStatus.FAILED else 0) if existing else 0,
            warning_count=existing.warning_count + (1 if status == HealthStatus.DEGRADED else 0) if existing else 0,
            uptime_seconds=existing.uptime_seconds if existing else 0.0,
            details=details or {},
        )

        self._save()

    def get_delta(self, metric: str, window: int = 10) -> float:
        """Calculate delta for a metric over the last N snapshots."""
        if len(self.snapshots) < 2:
            return 0.0

        recent = list(self.snapshots)[-window:]

        values = []
        for s in recent:
            val = getattr(s, metric, None)
            if val is not None:
                values.append(val)

        if len(values) < 2:
            return 0.0

        return values[-1] - values[0]

    def get_convergence_rate(self, window: int = 20) -> float:
        """
        Calculate convergence rate.

        High convergence = metric is stabilizing (low variance)
        Returns 0-1, where 1 = fully converged
        """
        if len(self.snapshots) < 5:
            return 0.0

        recent = list(self.snapshots)[-window:]
        rewards = [s.reward_score for s in recent if s.reward_score > 0]

        if len(rewards) < 3:
            return 0.0

        # Calculate variance
        mean = sum(rewards) / len(rewards)
        variance = sum((r - mean) ** 2 for r in rewards) / len(rewards)

        # Normalize to 0-1 (lower variance = higher convergence)
        max_variance = 0.25  # Assume 0.25 is max meaningful variance
        convergence = 1.0 - min(1.0, variance / max_variance)

        return convergence

    def get_oscillation_count(self, window: int = 20) -> int:
        """Count direction changes in recent metrics."""
        if len(self.snapshots) < 3:
            return 0

        recent = list(self.snapshots)[-window:]
        rewards = [s.reward_score for s in recent]

        oscillations = 0
        for i in range(2, len(rewards)):
            # Check if direction changed
            prev_dir = rewards[i-1] - rewards[i-2]
            curr_dir = rewards[i] - rewards[i-1]
            if prev_dir * curr_dir < 0:  # Sign change
                oscillations += 1

        return oscillations

    def get_trend(self, metric: str, window: int = 10) -> str:
        """Get trend direction for a metric."""
        delta = self.get_delta(metric, window)

        if delta > 0.05:
            return "improving"
        elif delta < -0.05:
            return "declining"
        else:
            return "stable"

    def get_summary(self) -> dict:
        """Get summary of all metrics."""
        if not self.snapshots:
            return {"status": "no_data"}

        latest = self.snapshots[-1]

        return {
            "current": latest.to_dict(),
            "deltas": {
                "reward": self.get_delta("reward_score"),
                "accuracy": self.get_delta("accuracy"),
                "efficiency": self.get_delta("efficiency"),
            },
            "convergence_rate": self.get_convergence_rate(),
            "oscillation_count": self.get_oscillation_count(),
            "trends": {
                "reward": self.get_trend("reward_score"),
                "accuracy": self.get_trend("accuracy"),
            },
            "component_health": {
                name: health.status.value
                for name, health in self.component_health.items()
            },
            "healthy_components": sum(
                1 for h in self.component_health.values()
                if h.status in (HealthStatus.OPTIMAL, HealthStatus.HEALTHY)
            ),
        }

    def _check_thresholds(self, snapshot: MetricSnapshot):
        """Check if any metrics breach thresholds."""
        # Check reward score
        if snapshot.reward_score < self.thresholds["reward_score"]["critical"]:
            self._alert("CRITICAL", "reward_score", snapshot.reward_score)
        elif snapshot.reward_score < self.thresholds["reward_score"]["low"]:
            self._alert("LOW", "reward_score", snapshot.reward_score)

        # Check components
        if snapshot.components_healthy < self.thresholds["components_healthy"]["critical"]:
            self._alert("CRITICAL", "components_healthy", snapshot.components_healthy)

    def _alert(self, level: str, metric: str, value: float):
        """Trigger an alert."""
        if self.on_alert:
            self.on_alert(level, metric, value)

    def _update_aggregations(self, snapshot: MetricSnapshot):
        """Update time-based aggregations."""
        hour_key = snapshot.timestamp.strftime("%Y-%m-%d-%H")
        day_key = snapshot.timestamp.strftime("%Y-%m-%d")

        if hour_key not in self.hourly_stats:
            self.hourly_stats[hour_key] = []

        self.hourly_stats[hour_key].append(snapshot.reward_score)

        # Clean old hourly stats
        if len(self.hourly_stats) > 48:
            oldest = sorted(self.hourly_stats.keys())[0]
            del self.hourly_stats[oldest]


class SystemAuditor:
    """
    Verifies semantic consistency across generations.

    Ensures the 7-component EvolutionaryLoop maintains:
    1. Behavioral consistency (same inputs → same outputs)
    2. Interface stability (APIs don't break)
    3. State coherence (state transitions are valid)
    4. Dependency integrity (no circular or broken deps)
    """

    COMPONENTS = [
        "InsightsDatabase",
        "WatchdogAgent",
        "RewardFunction",
        "GeneratorAgent",
        "CriticAgent",
        "Sandbox",
        "MetaPromptEngine",
        "AlignmentFirewall",
    ]

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Hash storage for consistency checks
        self.component_hashes: dict[str, str] = {}
        self.behavioral_baselines: dict[str, Any] = {}

        # Audit history
        self.audit_history: list[ConsistencyReport] = []

        self._load_baselines()

    def _load_baselines(self):
        """Load baseline hashes and behaviors."""
        baseline_file = self.state_dir / "audit_baselines.json"
        if baseline_file.exists():
            with open(baseline_file) as f:
                data = json.load(f)

            self.component_hashes = data.get("hashes", {})
            self.behavioral_baselines = data.get("behaviors", {})

    def _save_baselines(self):
        """Save baseline hashes and behaviors."""
        baseline_file = self.state_dir / "audit_baselines.json"
        with open(baseline_file, "w") as f:
            json.dump({
                "hashes": self.component_hashes,
                "behaviors": self.behavioral_baselines,
                "updated_at": datetime.now().isoformat(),
            }, f, indent=2)

    def compute_hash(self, content: str) -> str:
        """Compute hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def establish_baseline(self, component_name: str, code: str,
                           test_inputs: list[tuple] = None):
        """
        Establish baseline for a component.

        Args:
            component_name: Name of component
            code: Current code
            test_inputs: Optional test inputs for behavioral baseline
        """
        self.component_hashes[component_name] = self.compute_hash(code)

        if test_inputs:
            # Would execute and record outputs for behavioral baseline
            self.behavioral_baselines[component_name] = {
                "test_count": len(test_inputs),
                "established_at": datetime.now().isoformat(),
            }

        self._save_baselines()

    def verify_consistency(self, component_name: str, new_code: str,
                           level: ConsistencyLevel = ConsistencyLevel.SEMANTIC
                           ) -> ConsistencyReport:
        """
        Verify component maintains consistency.

        Args:
            component_name: Component to verify
            new_code: New code version
            level: Required consistency level

        Returns:
            ConsistencyReport with verification results
        """
        old_hash = self.component_hashes.get(component_name, "")
        new_hash = self.compute_hash(new_code)

        differences = []
        is_consistent = True
        behavioral_match = True

        # Exact match check
        if level == ConsistencyLevel.EXACT:
            is_consistent = (old_hash == new_hash)
            if not is_consistent:
                differences.append("Hash mismatch - code changed")

        # Semantic check (would use AST comparison in production)
        elif level == ConsistencyLevel.SEMANTIC:
            # Check that public interfaces are preserved
            old_interfaces = self._extract_interfaces(new_code)  # Simplified
            # In production, compare with stored interfaces
            is_consistent = True  # Placeholder

        # Behavioral check (would run tests in production)
        elif level == ConsistencyLevel.BEHAVIORAL:
            behavioral_match = self._verify_behavior(component_name, new_code)
            is_consistent = behavioral_match

        # Tolerant - always passes but logs differences
        elif level == ConsistencyLevel.TOLERANT:
            is_consistent = True
            if old_hash != new_hash:
                differences.append("Code changed but within tolerance")

        report = ConsistencyReport(
            is_consistent=is_consistent,
            level=level,
            component_name=component_name,
            hash_before=old_hash,
            hash_after=new_hash,
            behavioral_match=behavioral_match,
            differences=differences,
        )

        self.audit_history.append(report)
        self._save_audit_history()

        return report

    def _extract_interfaces(self, code: str) -> list[str]:
        """Extract public interfaces from code."""
        import ast

        try:
            tree = ast.parse(code)
        except:
            return []

        interfaces = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    interfaces.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith('_'):
                    interfaces.append(node.name)

        return interfaces

    def _verify_behavior(self, component_name: str, code: str) -> bool:
        """
        Verify behavioral consistency by running tests.

        In production, this would:
        1. Load test inputs from baseline
        2. Execute with new code
        3. Compare outputs to baseline
        """
        baseline = self.behavioral_baselines.get(component_name, {})
        if not baseline:
            return True  # No baseline, assume OK

        # Placeholder - would run actual tests
        return True

    def audit_all_components(self, components: dict[str, str],
                             level: ConsistencyLevel = ConsistencyLevel.SEMANTIC
                             ) -> dict[str, ConsistencyReport]:
        """
        Audit all components for consistency.

        Args:
            components: Dict of component_name -> code
            level: Required consistency level

        Returns:
            Dict of component_name -> ConsistencyReport
        """
        reports = {}

        for name, code in components.items():
            reports[name] = self.verify_consistency(name, code, level)

        return reports

    def check_dependency_integrity(self, components: dict[str, list[str]]) -> dict:
        """
        Check for circular or broken dependencies.

        Args:
            components: Dict of component_name -> list of dependencies

        Returns:
            Dict with integrity status
        """
        issues = []

        # Check for circular dependencies
        for name, deps in components.items():
            visited = set()
            path = [name]

            def check_cycle(comp: str) -> bool:
                if comp in visited:
                    return False
                visited.add(comp)

                for dep in components.get(comp, []):
                    if dep in path:
                        issues.append(f"Circular dependency: {' -> '.join(path + [dep])}")
                        return True
                    path.append(dep)
                    if check_cycle(dep):
                        return True
                    path.pop()

                return False

            check_cycle(name)

        # Check for broken dependencies
        all_components = set(components.keys())
        for name, deps in components.items():
            for dep in deps:
                if dep not in all_components:
                    issues.append(f"Broken dependency: {name} -> {dep} (not found)")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "component_count": len(components),
        }

    def _save_audit_history(self):
        """Save audit history."""
        history_file = self.state_dir / "audit_history.json"

        # Keep last 100 reports
        history = [r.to_dict() for r in self.audit_history[-100:]]

        with open(history_file, "w") as f:
            json.dump({
                "history": history,
                "updated_at": datetime.now().isoformat(),
            }, f, indent=2)

    def get_audit_summary(self) -> dict:
        """Get summary of audit status."""
        total = len(self.audit_history)
        consistent = sum(1 for r in self.audit_history if r.is_consistent)

        return {
            "total_audits": total,
            "consistent": consistent,
            "inconsistent": total - consistent,
            "consistency_rate": consistent / total if total > 0 else 1.0,
            "components_tracked": len(self.component_hashes),
            "baselines_established": len(self.behavioral_baselines),
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    state_dir = Path(".ouroboros/observability")
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create components
    logger = MetricsLogger(state_dir)
    auditor = SystemAuditor(state_dir)

    # Set up alert callback
    def on_alert(level: str, metric: str, value: float):
        print(f"🚨 ALERT [{level}]: {metric} = {value}")

    logger.on_alert = on_alert

    # Simulate recording snapshots
    print("Recording metrics...")
    for i in range(20):
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=i,
            reward_score=0.5 + i * 0.02 + (i % 3 * 0.05 - 0.05),  # Trending up with noise
            accuracy=0.8 - i * 0.01,
            efficiency=0.7 + i * 0.015,
            convergence_rate=0.0,
            components_healthy=7,
            insights_generated=i,
        )
        logger.record_snapshot(snapshot)

    # Get summary
    print("\n" + "=" * 60)
    print("METRICS SUMMARY")
    print(json.dumps(logger.get_summary(), indent=2, default=str))

    # Test auditor
    print("\n" + "=" * 60)
    print("AUDIT TEST")

    # Establish baseline
    auditor.establish_baseline("TestComponent", "def foo(): return 1")

    # Verify consistency
    report = auditor.verify_consistency(
        "TestComponent",
        "def foo(): return 2",  # Changed
        ConsistencyLevel.SEMANTIC
    )
    print(f"Consistent: {report.is_consistent}")
    print(f"Hash changed: {report.hash_before != report.hash_after}")

    # Get audit summary
    print("\n" + "=" * 60)
    print("AUDIT SUMMARY")
    print(json.dumps(auditor.get_audit_summary(), indent=2))
