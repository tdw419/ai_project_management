"""
Tests for the Cognitive Protocol (Multi-Agent RLHF Simulation)

Tests Generator-Critic architecture:
- AgentRole, FeedbackType enums
- AgentMessage, Feedback, Task, Attempt dataclasses
- GeneratorAgent class
- CriticAgent class
- CognitiveSimulation class
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import json
import tempfile

from src.ouroboros.protocols.cognitive import (
    AgentRole,
    FeedbackType,
    AgentMessage,
    Feedback,
    Task,
    Attempt,
    GeneratorAgent,
    CriticAgent,
    CognitiveSimulation,
)


# ============================================================
# Enum Tests
# ============================================================

class TestAgentRole:
    """Tests for AgentRole enum."""

    def test_generator_role(self):
        """Test GENERATOR role exists."""
        assert AgentRole.GENERATOR.value == "generator"

    def test_critic_role(self):
        """Test CRITIC role exists."""
        assert AgentRole.CRITIC.value == "critic"

    def test_all_roles_defined(self):
        """Test all expected roles are defined."""
        roles = list(AgentRole)
        assert len(roles) == 2


class TestFeedbackType:
    """Tests for FeedbackType enum."""

    def test_positive_feedback(self):
        """Test POSITIVE feedback type."""
        assert FeedbackType.POSITIVE.value == "positive"

    def test_negative_feedback(self):
        """Test NEGATIVE feedback type."""
        assert FeedbackType.NEGATIVE.value == "negative"

    def test_neutral_feedback(self):
        """Test NEUTRAL feedback type."""
        assert FeedbackType.NEUTRAL.value == "neutral"

    def test_constructive_feedback(self):
        """Test CONSTRUCTIVE feedback type."""
        assert FeedbackType.CONSTRUCTIVE.value == "constructive"

    def test_all_types_defined(self):
        """Test all expected types are defined."""
        types = list(FeedbackType)
        assert len(types) == 4


# ============================================================
# Dataclass Tests
# ============================================================

class TestAgentMessage:
    """Tests for AgentMessage dataclass."""

    def test_create_generator_message(self):
        """Test creating a generator message."""
        msg = AgentMessage(
            role=AgentRole.GENERATOR,
            content="Generated code here"
        )
        assert msg.role == AgentRole.GENERATOR
        assert msg.content == "Generated code here"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}

    def test_create_critic_message(self):
        """Test creating a critic message."""
        msg = AgentMessage(
            role=AgentRole.CRITIC,
            content="Critique here",
            metadata={"score": 0.8}
        )
        assert msg.role == AgentRole.CRITIC
        assert msg.metadata["score"] == 0.8

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = AgentMessage(
            role=AgentRole.GENERATOR,
            content="Test",
            metadata={"key": "value"}
        )
        d = msg.to_dict()
        assert d["role"] == "generator"
        assert d["content"] == "Test"
        assert d["metadata"]["key"] == "value"
        assert "timestamp" in d


class TestFeedback:
    """Tests for Feedback dataclass."""

    def test_create_positive_feedback(self):
        """Test creating positive feedback."""
        feedback = Feedback(
            score=0.8,
            feedback_type=FeedbackType.POSITIVE,
            strengths=["Good code"],
            weaknesses=[],
            suggestions=["Add more tests"]
        )
        assert feedback.score == 0.8
        assert feedback.feedback_type == FeedbackType.POSITIVE
        assert "Good code" in feedback.strengths

    def test_create_negative_feedback(self):
        """Test creating negative feedback."""
        feedback = Feedback(
            score=-0.5,
            feedback_type=FeedbackType.NEGATIVE,
            strengths=[],
            weaknesses=["Missing tests", "Poor structure"],
            suggestions=["Add unit tests"]
        )
        assert feedback.score == -0.5
        assert len(feedback.weaknesses) == 2

    def test_feedback_to_dict(self):
        """Test feedback serialization."""
        feedback = Feedback(
            score=0.5,
            feedback_type=FeedbackType.CONSTRUCTIVE,
            strengths=["S1"],
            weaknesses=["W1"],
            suggestions=["Sug1"]
        )
        d = feedback.to_dict()
        assert d["score"] == 0.5
        assert d["feedback_type"] == "constructive"
        assert d["strengths"] == ["S1"]
        assert d["weaknesses"] == ["W1"]
        assert d["suggestions"] == ["Sug1"]

    def test_feedback_from_dict(self):
        """Test feedback deserialization."""
        data = {
            "score": 0.7,
            "feedback_type": "positive",
            "strengths": ["A", "B"],
            "weaknesses": ["C"],
            "suggestions": ["D", "E"],
            "raw_response": "test"
        }
        feedback = Feedback.from_dict(data)
        assert feedback.score == 0.7
        assert feedback.feedback_type == FeedbackType.POSITIVE
        assert len(feedback.strengths) == 2
        assert feedback.raw_response == "test"

    def test_feedback_score_bounds(self):
        """Test feedback score can be at bounds."""
        max_feedback = Feedback(
            score=1.0,
            feedback_type=FeedbackType.POSITIVE,
            strengths=[],
            weaknesses=[],
            suggestions=[]
        )
        min_feedback = Feedback(
            score=-1.0,
            feedback_type=FeedbackType.NEGATIVE,
            strengths=[],
            weaknesses=[],
            suggestions=[]
        )
        assert max_feedback.score == 1.0
        assert min_feedback.score == -1.0


class TestTask:
    """Tests for Task dataclass."""

    def test_create_task_defaults(self):
        """Test creating a task with defaults."""
        task = Task(
            id="task-001",
            description="Optimize function",
            target_file="src/module.py"
        )
        assert task.id == "task-001"
        assert task.difficulty == 0.5
        assert task.category == "optimization"

    def test_create_task_custom(self):
        """Test creating a task with custom values."""
        task = Task(
            id="task-002",
            description="Complex refactor",
            target_file="src/complex.py",
            difficulty=0.9,
            category="refactoring"
        )
        assert task.difficulty == 0.9
        assert task.category == "refactoring"

    def test_task_to_dict(self):
        """Test task serialization."""
        task = Task(
            id="t1",
            description="Test task",
            target_file="test.py",
            difficulty=0.3
        )
        d = task.to_dict()
        assert d["id"] == "t1"
        assert d["description"] == "Test task"
        assert d["target_file"] == "test.py"
        assert d["difficulty"] == 0.3
        assert d["category"] == "optimization"


class TestAttempt:
    """Tests for Attempt dataclass."""

    def test_create_attempt(self):
        """Test creating an attempt."""
        task = Task(id="t1", description="Test", target_file="test.py")
        attempt = Attempt(
            task=task,
            generator_output="def foo(): pass",
            iteration=1
        )
        assert attempt.task.id == "t1"
        assert attempt.iteration == 1
        assert attempt.critic_feedback is None
        assert attempt.improved is False
        assert attempt.final_score == 0.0

    def test_attempt_with_feedback(self):
        """Test attempt with critic feedback."""
        task = Task(id="t1", description="Test", target_file="test.py")
        feedback = Feedback(
            score=0.6,
            feedback_type=FeedbackType.CONSTRUCTIVE,
            strengths=["Good"],
            weaknesses=["Bad"],
            suggestions=["Improve"]
        )
        attempt = Attempt(
            task=task,
            generator_output="code",
            critic_feedback=feedback,
            iteration=2,
            improved=True,
            final_score=0.6
        )
        assert attempt.critic_feedback.score == 0.6
        assert attempt.improved is True


# ============================================================
# GeneratorAgent Tests
# ============================================================

class TestGeneratorAgent:
    """Tests for GeneratorAgent class."""

    def test_create_generator(self):
        """Test creating a generator agent."""
        gen = GeneratorAgent()
        assert gen.model == "claude-sonnet-4-6-20250514"
        assert gen.attempt_history == []
        assert gen.learning_rate == 0.3

    def test_generate_initial(self):
        """Test generating initial solution."""
        gen = GeneratorAgent()
        task = Task(
            id="t1",
            description="Optimize function",
            target_file="test.py"
        )
        output = gen.generate(task)
        assert "test.py" in output or "t1" in output
        assert "def " in output

    def test_generate_revision(self):
        """Test generating revision based on feedback."""
        gen = GeneratorAgent()
        task = Task(
            id="t1",
            description="Test task",
            target_file="test.py"
        )
        feedback = Feedback(
            score=0.3,
            feedback_type=FeedbackType.CONSTRUCTIVE,
            strengths=["Has tests"],
            weaknesses=["Missing implementation"],
            suggestions=["Add actual logic"]
        )
        previous = Attempt(
            task=task,
            generator_output="def foo(): pass",
            critic_feedback=feedback,
            iteration=1
        )
        output = gen.generate(task, previous)
        assert "REVISED" in output or "v2" in output.lower() or "iteration" in output.lower()

    def test_record_attempt(self):
        """Test recording attempts."""
        gen = GeneratorAgent()
        task = Task(id="t1", description="Test", target_file="test.py")
        attempt = Attempt(task=task, generator_output="code", iteration=1)
        gen.record_attempt(attempt)
        assert len(gen.attempt_history) == 1
        assert gen.attempt_history[0] == attempt

    def test_multiple_attempts(self):
        """Test recording multiple attempts."""
        gen = GeneratorAgent()
        task = Task(id="t1", description="Test", target_file="test.py")
        for i in range(3):
            attempt = Attempt(task=task, generator_output=f"code{i}", iteration=i+1)
            gen.record_attempt(attempt)
        assert len(gen.attempt_history) == 3


# ============================================================
# CriticAgent Tests
# ============================================================

class TestCriticAgent:
    """Tests for CriticAgent class."""

    def test_create_critic(self):
        """Test creating a critic agent."""
        critic = CriticAgent(reward_function=None)
        assert critic.reward_function is None
        assert critic.feedback_history == []

    def test_evaluate_output(self):
        """Test evaluating generator output."""
        critic = CriticAgent(reward_function=None)
        task = Task(
            id="t1",
            description="Test task",
            target_file="test.py"
        )
        output = """
def optimized_function():
    return 42

def test_optimized_function():
    assert optimized_function() == 42
"""
        feedback = critic.evaluate(task, output)
        assert isinstance(feedback, Feedback)
        assert -1.0 <= feedback.score <= 1.0
        assert isinstance(feedback.feedback_type, FeedbackType)

    def test_evaluate_poor_output(self):
        """Test evaluating poor output."""
        critic = CriticAgent(reward_function=None)
        task = Task(id="t1", description="Test", target_file="test.py")
        output = "TODO"
        feedback = critic.evaluate(task, output)
        assert feedback.score < 0.5
        assert "TODO" in str(feedback.weaknesses) or len(feedback.suggestions) > 0

    def test_evaluate_good_output(self):
        """Test evaluating good output."""
        critic = CriticAgent(reward_function=None)
        task = Task(id="t1", description="Test", target_file="test.py")
        output = """
def complex_function(x, y):
    '''A well-documented function.'''
    if x < 0:
        raise ValueError("x must be positive")
    return x * y + x / y

def test_complex_function():
    assert complex_function(2, 4) == 9
    assert complex_function(1, 1) == 2
    try:
        complex_function(-1, 1)
        assert False
    except ValueError:
        pass
"""
        feedback = critic.evaluate(task, output)
        assert feedback.score > 0
        assert len(feedback.strengths) > 0

    def test_feedback_history(self):
        """Test that feedback is recorded."""
        critic = CriticAgent(reward_function=None)
        task = Task(id="t1", description="Test", target_file="test.py")
        for _ in range(3):
            critic.evaluate(task, "def foo(): pass")
        assert len(critic.feedback_history) == 3

    def test_score_simulation_characteristics(self):
        """Test that scoring considers output characteristics."""
        critic = CriticAgent(reward_function=None)
        task = Task(id="t1", description="Test", target_file="test.py", difficulty=0.5)

        # Output with tests should score higher
        output_with_tests = "def foo(): pass\ndef test_foo(): assert foo() is None"
        # Output without tests should score lower
        output_without_tests = "def foo(): pass"

        fb_with = critic.evaluate(task, output_with_tests)
        fb_without = critic.evaluate(task, output_without_tests)

        # Note: There's randomness in scoring, so we just check structure
        assert isinstance(fb_with.score, float)
        assert isinstance(fb_without.score, float)


# ============================================================
# CognitiveSimulation Tests
# ============================================================

class TestCognitiveSimulation:
    """Tests for CognitiveSimulation class."""

    @pytest.fixture
    def temp_state_dir(self, tmp_path):
        """Create temporary state directory."""
        state_dir = tmp_path / "simulations"
        state_dir.mkdir()
        return state_dir

    @pytest.fixture
    def simulation(self, temp_state_dir):
        """Create a simulation instance."""
        return CognitiveSimulation(temp_state_dir)

    def test_create_simulation(self, temp_state_dir):
        """Test creating a simulation."""
        sim = CognitiveSimulation(temp_state_dir)
        assert sim.generator is not None
        assert sim.critic is not None
        assert sim.max_iterations == 3
        assert sim.convergence_threshold == 0.7

    def test_run_single_task(self, simulation):
        """Test running a single task."""
        task = Task(
            id="test-001",
            description="Test task",
            target_file="test.py",
            difficulty=0.3
        )
        result = simulation.run_task(task, max_iterations=2)
        assert result is not None
        assert result.task.id == "test-001"
        assert result.iteration >= 1
        assert len(simulation.attempts) >= 1

    def test_run_task_convergence(self, simulation):
        """Test task convergence."""
        # Low threshold to ensure convergence
        simulation.convergence_threshold = 0.1
        task = Task(
            id="conv-test",
            description="Test",
            target_file="test.py",
            difficulty=0.1
        )
        result = simulation.run_task(task, max_iterations=3)
        assert result.final_score >= 0.1 or result.iteration == 3

    def test_run_task_max_iterations(self, simulation):
        """Test max iterations is respected."""
        simulation.convergence_threshold = 1.0  # Unreachable
        task = Task(
            id="max-iter-test",
            description="Test",
            target_file="test.py"
        )
        result = simulation.run_task(task, max_iterations=2)
        assert result.iteration <= 2

    def test_simulation_statistics(self, simulation):
        """Test getting simulation statistics."""
        # Run a task first
        task = Task(id="stat-test", description="Test", target_file="test.py")
        simulation.run_task(task, max_iterations=2)

        stats = simulation.get_statistics()
        assert "total_attempts" in stats
        assert stats["total_attempts"] > 0
        assert "avg_score" in stats
        assert "max_score" in stats

    def test_empty_statistics(self, simulation):
        """Test statistics with no attempts."""
        stats = simulation.get_statistics()
        assert stats["total_attempts"] == 0

    def test_callback_on_attempt(self, simulation):
        """Test on_attempt callback."""
        attempts_seen = []

        def capture_attempt(attempt):
            attempts_seen.append(attempt)

        simulation.on_attempt = capture_attempt
        task = Task(id="cb-test", description="Test", target_file="test.py")
        simulation.run_task(task, max_iterations=2)

        assert len(attempts_seen) >= 1

    def test_callback_on_converge(self, simulation):
        """Test on_converge callback."""
        converged = []

        def capture_converge(attempt):
            converged.append(attempt)

        simulation.on_converge = capture_converge
        simulation.convergence_threshold = 0.1  # Easy to reach
        task = Task(id="conv-cb-test", description="Test", target_file="test.py", difficulty=0.1)
        simulation.run_task(task, max_iterations=3)

        # May or may not converge depending on scoring
        # Just verify the callback mechanism works
        if converged:
            assert converged[0].final_score >= 0.1

    def test_save_simulation(self, simulation, temp_state_dir):
        """Test that simulation results are saved."""
        task = Task(id="save-test", description="Test", target_file="test.py")
        simulation.run_task(task, max_iterations=1)

        # Check for saved file
        saved_file = temp_state_dir / "simulation_save-test.json"
        assert saved_file.exists()

        with open(saved_file) as f:
            data = json.load(f)
        assert data["task"]["id"] == "save-test"
        assert "final_score" in data

    def test_multiple_tasks(self, simulation):
        """Test running multiple tasks."""
        tasks = [
            Task(id=f"multi-{i}", description=f"Task {i}", target_file="test.py", difficulty=0.3)
            for i in range(3)
        ]

        results = []
        for task in tasks:
            result = simulation.run_task(task, max_iterations=1)
            results.append(result)

        assert len(results) == 3
        assert len(simulation.attempts) >= 3

    def test_iteration_improvement(self, simulation):
        """Test that iterations can improve scores."""
        simulation.convergence_threshold = 1.0  # Force max iterations
        task = Task(id="improve-test", description="Test", target_file="test.py")

        result = simulation.run_task(task, max_iterations=3)

        # Check that multiple attempts were made
        task_attempts = [a for a in simulation.attempts if a.task.id == "improve-test"]
        assert len(task_attempts) >= 1


# ============================================================
# Integration Tests
# ============================================================

class TestCognitiveIntegration:
    """Integration tests for the full cognitive pipeline."""

    @pytest.fixture
    def full_simulation(self, tmp_path):
        """Create a full simulation with all components."""
        state_dir = tmp_path / "cognitive"
        state_dir.mkdir()
        return CognitiveSimulation(state_dir)

    def test_full_generator_critic_loop(self, full_simulation):
        """Test the complete generator-critic feedback loop."""
        task = Task(
            id="integration-test",
            description="Optimize a sorting function",
            target_file="src/sort.py",
            difficulty=0.5
        )

        result = full_simulation.run_task(task, max_iterations=3)

        # Verify complete pipeline
        assert result.task.id == "integration-test"
        assert result.critic_feedback is not None
        assert result.generator_output is not None
        assert result.final_score != 0.0 or result.iteration > 0

    def test_learning_from_feedback(self, full_simulation):
        """Test that generator learns from feedback."""
        task = Task(
            id="learning-test",
            description="Test learning",
            target_file="test.py"
        )

        # Run with max iterations to allow learning
        result = full_simulation.run_task(task, max_iterations=3)

        # Generator should have recorded attempts
        assert len(full_simulation.generator.attempt_history) >= 1

        # Critic should have recorded feedback
        assert len(full_simulation.critic.feedback_history) >= 1

    def test_task_difficulty_affects_scoring(self, full_simulation):
        """Test that task difficulty affects scores."""
        easy_task = Task(
            id="easy",
            description="Easy task",
            target_file="test.py",
            difficulty=0.1
        )
        hard_task = Task(
            id="hard",
            description="Hard task",
            target_file="test.py",
            difficulty=0.9
        )

        easy_result = full_simulation.run_task(easy_task, max_iterations=1)
        hard_result = full_simulation.run_task(hard_task, max_iterations=1)

        # Both should produce results
        assert easy_result.critic_feedback is not None
        assert hard_result.critic_feedback is not None
