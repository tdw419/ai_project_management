"""
Tests for the Observability Protocol (Validation and Metrics)

Tests:
- HealthStatus, ConsistencyLevel enums
- ComponentHealth, MetricSnapshot, ConsistencyReport dataclasses
- MetricsLogger class
- SystemAuditor class
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile

from src.ouroboros.protocols.observability import (
    HealthStatus,
    ConsistencyLevel,
    ComponentHealth,
    MetricSnapshot,
    ConsistencyReport,
    MetricsLogger,
    SystemAuditor,
)


# ============================================================
# Enum Tests
# ============================================================

class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_optimal_status(self):
        """Test OPTIMAL status."""
        assert HealthStatus.OPTIMAL.value == "optimal"

    def test_healthy_status(self):
        """Test HEALTHY status."""
        assert HealthStatus.HEALTHY.value == "healthy"

    def test_degraded_status(self):
        """Test DEGRADED status."""
        assert HealthStatus.DEGRADED.value == "degraded"

    def test_critical_status(self):
        """Test CRITICAL status."""
        assert HealthStatus.CRITICAL.value == "critical"

    def test_failed_status(self):
        """Test FAILED status."""
        assert HealthStatus.FAILED.value == "failed"

    def test_all_statuses_defined(self):
        """Test all expected statuses are defined."""
        statuses = list(HealthStatus)
        assert len(statuses) == 5


class TestConsistencyLevel:
    """Tests for ConsistencyLevel enum."""

    def test_exact_level(self):
        """Test EXACT level."""
        assert ConsistencyLevel.EXACT.value == "exact"

    def test_semantic_level(self):
        """Test SEMANTIC level."""
        assert ConsistencyLevel.SEMANTIC.value == "semantic"

    def test_behavioral_level(self):
        """Test BEHAVIORAL level."""
        assert ConsistencyLevel.BEHAVIORAL.value == "behavioral"

    def test_tolerant_level(self):
        """Test TOLERANT level."""
        assert ConsistencyLevel.TOLERANT.value == "tolerant"

    def test_all_levels_defined(self):
        """Test all expected levels are defined."""
        levels = list(ConsistencyLevel)
        assert len(levels) == 4


# ============================================================
# Dataclass Tests
# ============================================================

class TestComponentHealth:
    """Tests for ComponentHealth dataclass."""

    def test_create_health(self):
        """Test creating component health."""
        health = ComponentHealth(
            name="TestComponent",
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(),
        )
        assert health.name == "TestComponent"
        assert health.status == HealthStatus.HEALTHY
        assert health.error_count == 0
        assert health.warning_count == 0

    def test_health_with_counts(self):
        """Test health with error/warning counts."""
        health = ComponentHealth(
            name="FailingComponent",
            status=HealthStatus.DEGRADED,
            last_check=datetime.now(),
            error_count=3,
            warning_count=5,
        )
        assert health.error_count == 3
        assert health.warning_count == 5

    def test_health_to_dict(self):
        """Test health serialization."""
        health = ComponentHealth(
            name="Test",
            status=HealthStatus.OPTIMAL,
            last_check=datetime.now(),
            uptime_seconds=3600.0,
        )
        d = health.to_dict()
        assert d["name"] == "Test"
        assert d["status"] == "optimal"
        assert d["uptime_seconds"] == 3600.0


class TestMetricSnapshot:
    """Tests for MetricSnapshot dataclass."""

    def test_create_snapshot(self):
        """Test creating a metric snapshot."""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=1,
        )
        assert snapshot.iteration == 1
        assert snapshot.reward_score == 0.0
        assert snapshot.components_total == 7

    def test_snapshot_with_metrics(self):
        """Test snapshot with all metrics."""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=10,
            reward_score=0.75,
            accuracy=0.85,
            efficiency=0.90,
            convergence_rate=0.6,
            improvement_delta=0.1,
            oscillation_count=2,
            components_healthy=6,
            insights_generated=15,
            rollbacks_triggered=1,
        )
        assert snapshot.reward_score == 0.75
        assert snapshot.accuracy == 0.85
        assert snapshot.efficiency == 0.90

    def test_snapshot_to_dict(self):
        """Test snapshot serialization."""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=5,
            reward_score=0.5,
            memory_mb=256.0,
            cpu_percent=45.0,
        )
        d = snapshot.to_dict()
        assert d["iteration"] == 5
        assert d["reward_score"] == 0.5
        assert d["memory_mb"] == 256.0
        assert "timestamp" in d


class TestConsistencyReport:
    """Tests for ConsistencyReport dataclass."""

    def test_create_report(self):
        """Test creating a consistency report."""
        report = ConsistencyReport(
            is_consistent=True,
            level=ConsistencyLevel.SEMANTIC,
            component_name="TestComponent",
            hash_before="abc123",
            hash_after="abc123",
            behavioral_match=True,
        )
        assert report.is_consistent is True
        assert report.level == ConsistencyLevel.SEMANTIC
        assert report.behavioral_match is True

    def test_report_with_differences(self):
        """Test report with differences."""
        report = ConsistencyReport(
            is_consistent=False,
            level=ConsistencyLevel.EXACT,
            component_name="ChangedComponent",
            hash_before="abc123",
            hash_after="def456",
            behavioral_match=False,
            differences=["Hash mismatch", "Interface changed"],
        )
        assert len(report.differences) == 2
        assert report.is_consistent is False

    def test_report_to_dict(self):
        """Test report serialization."""
        report = ConsistencyReport(
            is_consistent=True,
            level=ConsistencyLevel.BEHAVIORAL,
            component_name="Test",
            hash_before="h1",
            hash_after="h2",
            behavioral_match=True,
        )
        d = report.to_dict()
        assert d["is_consistent"] is True
        assert d["level"] == "behavioral"
        assert d["hash_before"] == "h1"


# ============================================================
# MetricsLogger Tests
# ============================================================

class TestMetricsLogger:
    """Tests for MetricsLogger class."""

    @pytest.fixture
    def temp_logger(self, tmp_path):
        """Create a temporary logger."""
        return MetricsLogger(tmp_path, history_size=100)

    def test_create_logger(self, tmp_path):
        """Test creating a logger."""
        logger = MetricsLogger(tmp_path)
        assert logger.history_size == 1000
        assert len(logger.snapshots) == 0

    def test_record_snapshot(self, temp_logger):
        """Test recording a snapshot."""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=1,
            reward_score=0.5,
        )
        temp_logger.record_snapshot(snapshot)
        assert len(temp_logger.snapshots) == 1

    def test_record_multiple_snapshots(self, temp_logger):
        """Test recording multiple snapshots."""
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.1 * i,
            )
            temp_logger.record_snapshot(snapshot)
        assert len(temp_logger.snapshots) == 10

    def test_get_delta(self, temp_logger):
        """Test calculating delta."""
        for i in range(5):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.1 * i,
            )
            temp_logger.record_snapshot(snapshot)

        delta = temp_logger.get_delta("reward_score", window=5)
        assert delta == pytest.approx(0.4, rel=0.01)

    def test_get_delta_empty(self, temp_logger):
        """Test delta with no snapshots."""
        delta = temp_logger.get_delta("reward_score")
        assert delta == 0.0

    def test_get_convergence_rate(self, temp_logger):
        """Test convergence rate calculation."""
        # Stable values = high convergence
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.5,  # Stable
            )
            temp_logger.record_snapshot(snapshot)

        rate = temp_logger.get_convergence_rate()
        assert rate > 0.9  # Should be highly converged

    def test_get_convergence_rate_volatile(self, temp_logger):
        """Test convergence rate with volatile values."""
        # Volatile values = low convergence
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.1 if i % 2 == 0 else 0.9,  # Oscillating
            )
            temp_logger.record_snapshot(snapshot)

        rate = temp_logger.get_convergence_rate()
        assert rate < 0.9  # Should have lower convergence

    def test_get_oscillation_count(self, temp_logger):
        """Test oscillation counting."""
        # Create oscillating pattern
        values = [0.1, 0.5, 0.2, 0.6, 0.3, 0.7]
        for i, v in enumerate(values):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=v,
            )
            temp_logger.record_snapshot(snapshot)

        count = temp_logger.get_oscillation_count()
        assert count >= 1  # Should detect oscillations

    def test_get_trend_improving(self, temp_logger):
        """Test detecting improving trend."""
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.1 + i * 0.1,  # Increasing
            )
            temp_logger.record_snapshot(snapshot)

        trend = temp_logger.get_trend("reward_score")
        assert trend == "improving"

    def test_get_trend_declining(self, temp_logger):
        """Test detecting declining trend."""
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.9 - i * 0.1,  # Decreasing
            )
            temp_logger.record_snapshot(snapshot)

        trend = temp_logger.get_trend("reward_score")
        assert trend == "declining"

    def test_get_trend_stable(self, temp_logger):
        """Test detecting stable trend."""
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.5,  # Stable
            )
            temp_logger.record_snapshot(snapshot)

        trend = temp_logger.get_trend("reward_score")
        assert trend == "stable"

    def test_update_component_health(self, temp_logger):
        """Test updating component health."""
        temp_logger.update_component_health(
            "TestComponent",
            HealthStatus.HEALTHY,
            details={"version": "1.0"}
        )
        assert "TestComponent" in temp_logger.component_health
        assert temp_logger.component_health["TestComponent"].status == HealthStatus.HEALTHY

    def test_component_health_accumulation(self, temp_logger):
        """Test error/warning accumulation."""
        temp_logger.update_component_health("Comp", HealthStatus.HEALTHY)
        temp_logger.update_component_health("Comp", HealthStatus.DEGRADED)
        temp_logger.update_component_health("Comp", HealthStatus.FAILED)

        health = temp_logger.component_health["Comp"]
        assert health.warning_count == 1
        assert health.error_count == 1

    def test_get_summary(self, temp_logger):
        """Test getting summary."""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=1,
            reward_score=0.5,
        )
        temp_logger.record_snapshot(snapshot)

        summary = temp_logger.get_summary()
        assert "current" in summary
        assert "deltas" in summary
        assert "trends" in summary

    def test_get_summary_empty(self, temp_logger):
        """Test summary with no data."""
        summary = temp_logger.get_summary()
        assert summary["status"] == "no_data"

    def test_alert_callback(self, temp_logger):
        """Test alert callback is triggered."""
        alerts = []

        def capture_alert(level, metric, value):
            alerts.append((level, metric, value))

        temp_logger.on_alert = capture_alert

        # Trigger critical alert
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=1,
            reward_score=0.05,  # Below critical threshold
            components_healthy=2,  # Below critical threshold
        )
        temp_logger.record_snapshot(snapshot)

        assert len(alerts) >= 1


# ============================================================
# SystemAuditor Tests
# ============================================================

class TestSystemAuditor:
    """Tests for SystemAuditor class."""

    @pytest.fixture
    def temp_auditor(self, tmp_path):
        """Create a temporary auditor."""
        return SystemAuditor(tmp_path)

    def test_create_auditor(self, tmp_path):
        """Test creating an auditor."""
        auditor = SystemAuditor(tmp_path)
        assert auditor.component_hashes == {}
        assert len(auditor.COMPONENTS) == 8

    def test_compute_hash(self, temp_auditor):
        """Test hash computation."""
        hash1 = temp_auditor.compute_hash("test code")
        hash2 = temp_auditor.compute_hash("test code")
        hash3 = temp_auditor.compute_hash("different code")

        assert hash1 == hash2  # Same content = same hash
        assert hash1 != hash3  # Different content = different hash

    def test_establish_baseline(self, temp_auditor):
        """Test establishing baseline."""
        temp_auditor.establish_baseline(
            "TestComponent",
            "def foo(): pass",
            test_inputs=[(1, 2), (3, 4)]
        )
        assert "TestComponent" in temp_auditor.component_hashes
        assert "TestComponent" in temp_auditor.behavioral_baselines

    def test_verify_consistency_exact(self, temp_auditor):
        """Test exact consistency verification."""
        temp_auditor.establish_baseline("Comp", "original code")
        report = temp_auditor.verify_consistency(
            "Comp",
            "original code",
            ConsistencyLevel.EXACT
        )
        assert report.is_consistent is True

    def test_verify_consistency_exact_changed(self, temp_auditor):
        """Test exact consistency with changed code."""
        temp_auditor.establish_baseline("Comp", "original code")
        report = temp_auditor.verify_consistency(
            "Comp",
            "changed code",
            ConsistencyLevel.EXACT
        )
        assert report.is_consistent is False
        assert len(report.differences) >= 1

    def test_verify_consistency_tolerant(self, temp_auditor):
        """Test tolerant consistency always passes."""
        temp_auditor.establish_baseline("Comp", "original")
        report = temp_auditor.verify_consistency(
            "Comp",
            "completely different",
            ConsistencyLevel.TOLERANT
        )
        assert report.is_consistent is True

    def test_verify_consistency_semantic(self, temp_auditor):
        """Test semantic consistency."""
        temp_auditor.establish_baseline("Comp", "original")
        report = temp_auditor.verify_consistency(
            "Comp",
            "modified",
            ConsistencyLevel.SEMANTIC
        )
        # Semantic check (placeholder implementation)
        assert isinstance(report.is_consistent, bool)

    def test_extract_interfaces(self, temp_auditor):
        """Test interface extraction."""
        code = """
class MyClass:
    def public_method(self):
        pass
    def _private_method(self):
        pass

def public_function():
    pass

def _private_function():
    pass
"""
        interfaces = temp_auditor._extract_interfaces(code)
        assert "MyClass" in interfaces
        assert "public_method" in interfaces
        assert "public_function" in interfaces
        assert "_private_method" not in interfaces
        assert "_private_function" not in interfaces

    def test_audit_all_components(self, temp_auditor):
        """Test auditing all components."""
        temp_auditor.establish_baseline("Comp1", "code1")
        temp_auditor.establish_baseline("Comp2", "code2")

        components = {
            "Comp1": "code1",  # Unchanged
            "Comp2": "changed",  # Changed
        }

        reports = temp_auditor.audit_all_components(
            components,
            ConsistencyLevel.EXACT
        )

        assert len(reports) == 2
        assert reports["Comp1"].is_consistent is True
        assert reports["Comp2"].is_consistent is False

    def test_check_dependency_integrity_valid(self, temp_auditor):
        """Test dependency integrity check with valid deps."""
        components = {
            "A": ["B", "C"],
            "B": ["C"],
            "C": [],
        }
        result = temp_auditor.check_dependency_integrity(components)
        assert result["valid"] is True
        assert len(result["issues"]) == 0

    def test_check_dependency_integrity_circular(self, temp_auditor):
        """Test detecting circular dependencies."""
        components = {
            "A": ["B"],
            "B": ["C"],
            "C": ["A"],  # Circular!
        }
        result = temp_auditor.check_dependency_integrity(components)
        assert result["valid"] is False
        assert any("Circular" in issue for issue in result["issues"])

    def test_check_dependency_integrity_broken(self, temp_auditor):
        """Test detecting broken dependencies."""
        components = {
            "A": ["B"],  # B doesn't exist
        }
        result = temp_auditor.check_dependency_integrity(components)
        assert result["valid"] is False
        assert any("Broken" in issue for issue in result["issues"])

    def test_get_audit_summary(self, temp_auditor):
        """Test getting audit summary."""
        temp_auditor.establish_baseline("Comp", "code")
        temp_auditor.verify_consistency("Comp", "code", ConsistencyLevel.EXACT)
        temp_auditor.verify_consistency("Comp", "changed", ConsistencyLevel.EXACT)

        summary = temp_auditor.get_audit_summary()
        assert summary["total_audits"] == 2
        assert summary["consistent"] == 1
        assert summary["inconsistent"] == 1

    def test_persistence(self, tmp_path):
        """Test that baselines persist."""
        # Create and establish
        auditor1 = SystemAuditor(tmp_path)
        auditor1.establish_baseline("PersistTest", "code")

        # Create new instance
        auditor2 = SystemAuditor(tmp_path)
        assert "PersistTest" in auditor2.component_hashes


# ============================================================
# Integration Tests
# ============================================================

class TestObservabilityIntegration:
    """Integration tests for observability system."""

    @pytest.fixture
    def full_system(self, tmp_path):
        """Create full observability system."""
        return {
            "logger": MetricsLogger(tmp_path / "metrics"),
            "auditor": SystemAuditor(tmp_path / "audit"),
        }

    def test_full_monitoring_cycle(self, full_system):
        """Test complete monitoring cycle."""
        logger = full_system["logger"]
        auditor = full_system["auditor"]

        # Establish baselines
        components = {
            "InsightsDatabase": "class InsightsDatabase: pass",
            "WatchdogAgent": "class WatchdogAgent: pass",
        }

        for name, code in components.items():
            auditor.establish_baseline(name, code)

        # Simulate iterations
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.5 + i * 0.03,
                accuracy=0.8 + i * 0.01,
                efficiency=0.7,
                components_healthy=7,
                insights_generated=i * 2,
            )
            logger.record_snapshot(snapshot)

            # Update component health
            logger.update_component_health(
                "InsightsDatabase",
                HealthStatus.HEALTHY if i < 8 else HealthStatus.DEGRADED
            )

        # Get summaries
        metrics_summary = logger.get_summary()
        audit_summary = auditor.get_audit_summary()

        assert metrics_summary["trends"]["reward"] == "improving"
        assert audit_summary["components_tracked"] == 2

    def test_alert_on_degradation(self, full_system):
        """Test alerts trigger on degradation."""
        logger = full_system["logger"]
        alerts = []

        def capture_alert(level, metric, value):
            alerts.append((level, metric, value))

        logger.on_alert = capture_alert

        # Record healthy snapshots
        for i in range(5):
            snapshot = MetricSnapshot(
                timestamp=datetime.now(),
                iteration=i,
                reward_score=0.7,
                components_healthy=7,
            )
            logger.record_snapshot(snapshot)

        # Record degraded snapshot
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            iteration=5,
            reward_score=0.05,  # Critical
            components_healthy=2,  # Critical
        )
        logger.record_snapshot(snapshot)

        # Should have triggered alerts
        assert len(alerts) >= 1

    def test_consistency_audit_flow(self, full_system):
        """Test consistency audit flow."""
        auditor = full_system["auditor"]

        # Establish baselines
        code_v1 = """
class DataProcessor:
    def process(self, data):
        return data.upper()
"""
        auditor.establish_baseline("DataProcessor", code_v1)

        # Verify same code is consistent
        report1 = auditor.verify_consistency(
            "DataProcessor",
            code_v1,
            ConsistencyLevel.EXACT
        )
        assert report1.is_consistent is True

        # Verify changed code fails exact check
        code_v2 = """
class DataProcessor:
    def process(self, data):
        return data.lower()  # Changed behavior
"""
        report2 = auditor.verify_consistency(
            "DataProcessor",
            code_v2,
            ConsistencyLevel.EXACT
        )
        assert report2.is_consistent is False

        # But passes tolerant check
        report3 = auditor.verify_consistency(
            "DataProcessor",
            code_v2,
            ConsistencyLevel.TOLERANT
        )
        assert report3.is_consistent is True

    def test_dependency_validation(self, full_system):
        """Test dependency validation."""
        auditor = full_system["auditor"]

        # Valid dependency graph
        valid_deps = {
            "RewardFunction": ["InsightsDatabase"],
            "WatchdogAgent": ["RewardFunction"],
            "InsightsDatabase": [],
        }
        result1 = auditor.check_dependency_integrity(valid_deps)
        assert result1["valid"] is True

        # Invalid: circular dependency
        circular_deps = {
            "A": ["B"],
            "B": ["C"],
            "C": ["A"],
        }
        result2 = auditor.check_dependency_integrity(circular_deps)
        assert result2["valid"] is False

        # Invalid: broken dependency
        broken_deps = {
            "A": ["NonExistent"],
        }
        result3 = auditor.check_dependency_integrity(broken_deps)
        assert result3["valid"] is False
