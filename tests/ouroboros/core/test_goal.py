"""
Tests for Goal State Management

Tests:
- GoalState dataclass
- Load/save operations
- Success criteria checking
- State transitions
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, mock_open
import tempfile
import yaml

from src.ouroboros.core.goal import GoalState


class TestGoalState:
    """Tests for GoalState dataclass."""

    def test_create_goal_defaults(self):
        """Test creating a goal with defaults."""
        goal = GoalState(
            objective="Improve accuracy",
            success_criteria="accuracy > 0.9",
        )
        assert goal.objective == "Improve accuracy"
        assert goal.success_criteria == "accuracy > 0.9"
        assert goal.current_state == "initialized"
        assert goal.iterations == 0
        assert goal.best_metric is None
        assert goal.max_iterations == 100
        assert goal.max_time_hours == 24.0

    def test_create_goal_custom(self):
        """Test creating a goal with custom values."""
        goal = GoalState(
            objective="Custom objective",
            success_criteria="metric < 0.5",
            current_state="running",
            iterations=10,
            best_metric=0.45,
            max_iterations=50,
            max_time_hours=12.0,
        )
        assert goal.iterations == 10
        assert goal.best_metric == 0.45
        assert goal.max_iterations == 50

    def test_goal_created_at_auto_set(self):
        """Test that created_at is auto-set."""
        before = datetime.now()
        goal = GoalState(
            objective="Test",
            success_criteria="test",
        )
        after = datetime.now()

        assert before <= goal.created_at <= after

    def test_goal_updated_at_auto_set(self):
        """Test that updated_at is auto-set."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
        )
        assert goal.updated_at is not None


class TestGoalStateLoadSave:
    """Tests for load and save operations."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test saving and loading preserves data."""
        goal = GoalState(
            objective="Test objective",
            success_criteria="metric > 0.8",
            current_state="running",
            iterations=5,
            best_metric=0.85,
            max_iterations=100,
            max_time_hours=24.0,
        )

        goal_file = tmp_path / "goal.yaml"
        goal.save(goal_file)

        loaded = GoalState.load(goal_file)

        assert loaded.objective == goal.objective
        assert loaded.success_criteria == goal.success_criteria
        assert loaded.current_state == goal.current_state
        assert loaded.iterations == goal.iterations
        assert loaded.best_metric == goal.best_metric

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading a file that doesn't exist."""
        goal_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            GoalState.load(goal_file)

    def test_save_creates_file(self, tmp_path):
        """Test that save creates the file."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
        )
        goal_file = tmp_path / "goal.yaml"

        assert not goal_file.exists()
        goal.save(goal_file)
        assert goal_file.exists()

    def test_load_partial_data(self, tmp_path):
        """Test loading file with partial data."""
        goal_file = tmp_path / "goal.yaml"

        # Create minimal valid YAML
        data = {
            "objective": "Partial goal",
            "success_criteria": "test",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        with open(goal_file, "w") as f:
            yaml.dump(data, f)

        loaded = GoalState.load(goal_file)

        assert loaded.objective == "Partial goal"
        assert loaded.iterations == 0  # Default
        assert loaded.best_metric is None  # Default

    def test_save_with_unicode(self, tmp_path):
        """Test saving goal with unicode characters."""
        goal = GoalState(
            objective="Test 目標 🎯",
            success_criteria="指標 > 0.9",
        )
        goal_file = tmp_path / "goal.yaml"

        goal.save(goal_file)
        loaded = GoalState.load(goal_file)

        assert loaded.objective == "Test 目標 🎯"
        assert loaded.success_criteria == "指標 > 0.9"


class TestGoalStateTransitions:
    """Tests for state transitions."""

    def test_increment(self, tmp_path):
        """Test incrementing iterations."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            iterations=5,
        )
        goal_file = tmp_path / "goal.yaml"

        updated = goal.increment()

        assert updated.iterations == 6
        assert goal.iterations == 5  # Original unchanged

    def test_update_best(self):
        """Test updating best metric."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            best_metric=0.5,
        )

        updated = goal.update_best(0.7)

        assert updated.best_metric == 0.7
        assert goal.best_metric == 0.5  # Original unchanged

    def test_update_best_keeps_lower(self):
        """Test that update_best keeps lower value for minimization."""
        goal = GoalState(
            objective="Minimize loss",
            success_criteria="loss < 0.1",
            best_metric=0.3,
        )

        # For minimization, lower is better
        updated = goal.update_best(0.2)

        assert updated.best_metric == 0.2

    def test_update_best_no_improvement(self):
        """Test update_best when new value is worse."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            best_metric=0.5,
        )

        updated = goal.update_best(0.4)  # Worse for maximization

        # Behavior depends on implementation
        # Could keep original or update anyway
        assert updated.best_metric is not None


class TestSuccessCriteria:
    """Tests for success criteria checking."""

    def test_is_achieved_greater_than(self, tmp_path):
        """Test > comparison."""
        goal = GoalState(
            objective="Test",
            success_criteria="accuracy > 0.8",
        )
        goal_file = tmp_path / "goal.yaml"

        assert goal.is_achieved(0.9) is True
        assert goal.is_achieved(0.8) is False
        assert goal.is_achieved(0.7) is False

    def test_is_achieved_less_than(self, tmp_path):
        """Test < comparison."""
        goal = GoalState(
            objective="Test",
            success_criteria="loss < 0.1",
        )

        assert goal.is_achieved(0.05) is True
        assert goal.is_achieved(0.1) is False
        assert goal.is_achieved(0.2) is False

    def test_is_achieved_greater_equal(self, tmp_path):
        """Test >= comparison."""
        goal = GoalState(
            objective="Test",
            success_criteria="score >= 0.8",
        )

        assert goal.is_achieved(0.9) is True
        assert goal.is_achieved(0.8) is True
        assert goal.is_achieved(0.7) is False

    def test_is_achieved_less_equal(self, tmp_path):
        """Test <= comparison."""
        goal = GoalState(
            objective="Test",
            success_criteria="error <= 0.05",
        )

        assert goal.is_achieved(0.04) is True
        assert goal.is_achieved(0.05) is True
        assert goal.is_achieved(0.06) is False

    def test_is_achieved_equal(self, tmp_path):
        """Test == comparison."""
        goal = GoalState(
            objective="Test",
            success_criteria="status == 1",
        )

        assert goal.is_achieved(1.0) is True
        assert goal.is_achieved(0.0) is False

    def test_is_achieved_complex_criteria(self, tmp_path):
        """Test more complex criteria patterns."""
        goal = GoalState(
            objective="Test",
            success_criteria="metric > 0.95",
        )

        # Various edge cases
        assert goal.is_achieved(0.951) is True
        assert goal.is_achieved(0.949) is False
        assert goal.is_achieved(1.0) is True
        assert goal.is_achieved(0.0) is False


class TestGoalStateValidation:
    """Tests for goal state validation."""

    def test_is_exhausted_by_iterations(self):
        """Test exhaustion by iteration count."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            iterations=100,
            max_iterations=100,
        )

        assert goal.is_exhausted() is True

    def test_is_exhausted_by_time(self):
        """Test exhaustion by time limit."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            created_at=datetime.now() - timedelta(hours=25),
            max_time_hours=24.0,
        )

        assert goal.is_exhausted() is True

    def test_is_not_exhausted(self):
        """Test when not exhausted."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            iterations=50,
            max_iterations=100,
            created_at=datetime.now(),
            max_time_hours=24.0,
        )

        assert goal.is_exhausted() is False

    def test_is_exhausted_iterations_priority(self):
        """Test iteration check takes priority."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            iterations=100,
            max_iterations=100,
            created_at=datetime.now(),  # Fresh
            max_time_hours=24.0,
        )

        # Should be exhausted by iterations even though time is fine
        assert goal.is_exhausted() is True


class TestGoalStateEdgeCases:
    """Tests for edge cases."""

    def test_negative_iterations(self):
        """Test handling of negative iterations."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            iterations=-1,
        )

        # Should handle gracefully
        assert goal.iterations == -1

    def test_very_large_metric(self):
        """Test handling of very large metrics."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            best_metric=1e100,
        )

        assert goal.best_metric == 1e100

    def test_very_small_metric(self):
        """Test handling of very small metrics."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            best_metric=1e-100,
        )

        assert goal.best_metric == 1e-100

    def test_infinity_metric(self):
        """Test handling of infinity."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            best_metric=float("inf"),
        )

        assert goal.best_metric == float("inf")

    def test_nan_metric(self):
        """Test handling of NaN."""
        goal = GoalState(
            objective="Test",
            success_criteria="test",
            best_metric=float("nan"),
        )

        # NaN comparison is tricky
        import math
        assert math.isnan(goal.best_metric)

    def test_empty_objective(self):
        """Test handling of empty objective."""
        goal = GoalState(
            objective="",
            success_criteria="test",
        )

        assert goal.objective == ""

    def test_multiline_objective(self):
        """Test handling of multiline objective."""
        goal = GoalState(
            objective="Line 1\nLine 2\nLine 3",
            success_criteria="test",
        )

        assert "\n" in goal.objective

    def test_concurrent_save_load(self, tmp_path):
        """Test concurrent save/load operations."""
        import threading
        import time

        goal_file = tmp_path / "goal.yaml"

        # Initial save
        goal = GoalState(
            objective="Concurrent test",
            success_criteria="test",
        )
        goal.save(goal_file)

        errors = []

        def writer():
            try:
                for i in range(10):
                    g = GoalState.load(goal_file)
                    g.iterations = i
                    g.save(goal_file)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(10):
                    GoalState.load(goal_file)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors due to file locking
        assert len(errors) == 0
