"""
Autonomous Reward Modeling Protocol

A reward function that learns to identify high-value actions
from state transitions and outcome feedback.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from enum import Enum
import json
import math


class ActionType(Enum):
    CODE_CHANGE = "code_change"
    TEST_ADDITION = "test_addition"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    EXPLORATION = "exploration"
    ROLLBACK = "rollback"


@dataclass
class StateSnapshot:
    """Snapshot of system state at a point in time."""
    iteration: int
    metric_score: float
    test_coverage: float
    error_count: int
    files_modified: int
    insights_gained: int
    timestamp: datetime = field(default_factory=datetime.now)

    def to_vector(self) -> list[float]:
        """Convert state to feature vector."""
        return [
            self.iteration / 100.0,  # Normalized iteration
            self.metric_score,
            self.test_coverage,
            self.error_count / 10.0,  # Normalized errors
            self.files_modified / 10.0,  # Normalized files
            self.insights_gained / 20.0,  # Normalized insights
        ]

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "metric_score": self.metric_score,
            "test_coverage": self.test_coverage,
            "error_count": self.error_count,
            "files_modified": self.files_modified,
            "insights_gained": self.insights_gained,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StateSnapshot":
        return cls(
            iteration=data["iteration"],
            metric_score=data["metric_score"],
            test_coverage=data["test_coverage"],
            error_count=data["error_count"],
            files_modified=data["files_modified"],
            insights_gained=data["insights_gained"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class Action:
    """An action taken by the agent."""
    action_type: ActionType
    description: str
    target: str  # File, module, or area affected
    parameters: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_vector(self) -> list[float]:
        """Convert action to feature vector (one-hot for type)."""
        type_vec = [0.0] * len(ActionType)
        type_vec[self.action_type.value[0]] = 1.0
        return type_vec

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "target": self.target,
            "parameters": self.parameters,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        return cls(
            action_type=ActionType(data["action_type"]),
            description=data["description"],
            target=data["target"],
            parameters=data.get("parameters", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class Transition:
    """A state-action-state transition with reward."""
    state_before: StateSnapshot
    action: Action
    state_after: StateSnapshot
    reward: float = 0.0
    outcome_success: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "state_before": self.state_before.to_dict(),
            "action": self.action.to_dict(),
            "state_after": self.state_after.to_dict(),
            "reward": self.reward,
            "outcome_success": self.outcome_success,
        }


@dataclass
class RewardWeights:
    """Learnable weights for reward calculation."""
    metric_improvement: float = 0.35
    coverage_improvement: float = 0.20
    error_reduction: float = 0.15
    insight_generation: float = 0.10
    exploration_bonus: float = 0.10
    efficiency_penalty: float = 0.10

    def to_list(self) -> list[float]:
        return [
            self.metric_improvement,
            self.coverage_improvement,
            self.error_reduction,
            self.insight_generation,
            self.exploration_bonus,
            self.efficiency_penalty,
        ]

    def from_list(self, weights: list[float]):
        self.metric_improvement = weights[0]
        self.coverage_improvement = weights[1]
        self.error_reduction = weights[2]
        self.insight_generation = weights[3]
        self.exploration_bonus = weights[4]
        self.efficiency_penalty = weights[5]

    def normalize(self):
        """Normalize weights to sum to 1.0."""
        total = sum(self.to_list())
        if total > 0:
            self.from_list([w / total for w in self.to_list()])


class RewardFunction:
    """
    Learns to assign scalar rewards to state transitions.

    The reward function:
    1. Computes immediate reward from state delta
    2. Learns from trajectory outcomes (success/failure)
    3. Adjusts weights based on feedback
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.weights = RewardWeights()
        self.trajectories: list[Transition] = []
        self.learning_rate = 0.1
        self.discount_factor = 0.95

        self._load()

    def _load(self):
        """Load learned weights and trajectories."""
        weights_file = self.state_dir / "reward_weights.json"
        if weights_file.exists():
            with open(weights_file) as f:
                data = json.load(f)
            self.weights.from_list(data.get("weights", self.weights.to_list()))
            self.weights.normalize()
            self.learning_rate = data.get("learning_rate", 0.1)

        trajectories_file = self.state_dir / "trajectories.json"
        if trajectories_file.exists():
            with open(trajectories_file) as f:
                data = json.load(f)
            self.trajectories = [
                Transition(
                    state_before=StateSnapshot.from_dict(t["state_before"]),
                    action=Action.from_dict(t["action"]),
                    state_after=StateSnapshot.from_dict(t["state_after"]),
                    reward=t["reward"],
                    outcome_success=t.get("outcome_success"),
                )
                for t in data.get("trajectories", [])
            ]

    def _save(self):
        """Persist weights and recent trajectories."""
        weights_file = self.state_dir / "reward_weights.json"
        with open(weights_file, "w") as f:
            json.dump({
                "weights": self.weights.to_list(),
                "learning_rate": self.learning_rate,
                "updated_at": datetime.now().isoformat(),
            }, f, indent=2)

        # Keep last 100 trajectories
        trajectories_file = self.state_dir / "trajectories.json"
        with open(trajectories_file, "w") as f:
            json.dump({
                "trajectories": [t.to_dict() for t in self.trajectories[-100:]],
            }, f, indent=2)

    def compute_reward(self, state_before: StateSnapshot,
                       action: Action,
                       state_after: StateSnapshot) -> float:
        """
        Compute scalar reward for a transition.

        Reward = w1*Δmetric + w2*Δcoverage + w3*Δerrors
               + w4*Δinsights + w5*exploration - w6*files_modified
        """
        # Delta features
        delta_metric = state_after.metric_score - state_before.metric_score
        delta_coverage = state_after.test_coverage - state_before.test_coverage
        delta_errors = state_before.error_count - state_after.error_count  # Negative = good
        delta_insights = state_after.insights_gained - state_before.insights_gained

        # Exploration bonus (trying new things)
        exploration_bonus = 0.1 if action.action_type == ActionType.EXPLORATION else 0.0

        # Efficiency penalty (modifying too many files)
        efficiency_penalty = state_after.files_modified * 0.01

        # Weighted sum
        reward = (
            self.weights.metric_improvement * delta_metric +
            self.weights.coverage_improvement * delta_coverage +
            self.weights.error_reduction * delta_errors +
            self.weights.insight_generation * delta_insights +
            self.weights.exploration_bonus * exploration_bonus -
            self.weights.efficiency_penalty * efficiency_penalty
        )

        return reward

    def record_transition(self, state_before: StateSnapshot,
                          action: Action,
                          state_after: StateSnapshot,
                          outcome_success: Optional[bool] = None) -> Transition:
        """Record a transition and compute its reward."""
        reward = self.compute_reward(state_before, action, state_after)

        transition = Transition(
            state_before=state_before,
            action=action,
            state_after=state_after,
            reward=reward,
            outcome_success=outcome_success,
        )

        self.trajectories.append(transition)
        self._save()

        return transition

    def learn_from_outcome(self, transition_id: int, success: bool):
        """
        Adjust weights based on outcome feedback.

        Uses gradient-like update:
        - If successful, increase weights for positive contributions
        - If failed, decrease weights for negative contributions
        """
        if transition_id >= len(self.trajectories):
            return

        transition = self.trajectories[transition_id]
        transition.outcome_success = success

        # Compute feature deltas
        state_before = transition.state_before
        state_after = transition.state_after

        deltas = [
            state_after.metric_score - state_before.metric_score,
            state_after.test_coverage - state_before.test_coverage,
            state_before.error_count - state_after.error_count,
            state_after.insights_gained - state_before.insights_gained,
            0.1 if transition.action.action_type == ActionType.EXPLORATION else 0.0,
            -state_after.files_modified * 0.01,
        ]

        # Update weights
        weights = self.weights.to_list()
        for i, (w, d) in enumerate(zip(weights, deltas)):
            if success:
                # Increase weight if feature was positive
                weights[i] = w + self.learning_rate * max(0, d)
            else:
                # Decrease weight if feature was negative
                weights[i] = w - self.learning_rate * max(0, -d)

        self.weights.from_list(weights)
        self.weights.normalize()
        self._save()

    def get_best_actions(self, current_state: StateSnapshot,
                         candidate_actions: list[Action]) -> list[tuple[Action, float]]:
        """
        Rank candidate actions by predicted reward.

        Returns list of (action, predicted_reward) sorted by reward.
        """
        predictions = []

        for action in candidate_actions:
            # Predict state after (simple heuristic)
            predicted_state = self._predict_state(current_state, action)
            predicted_reward = self.compute_reward(current_state, action, predicted_state)
            predictions.append((action, predicted_reward))

        # Sort by reward descending
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions

    def _predict_state(self, state: StateSnapshot, action: Action) -> StateSnapshot:
        """Predict state after taking an action (simple heuristic)."""
        # Base prediction: assume small improvement
        delta_metric = 0.01
        delta_coverage = 0.01 if action.action_type == ActionType.TEST_ADDITION else 0.0
        delta_errors = -0.1 if action.action_type == ActionType.CODE_CHANGE else 0.0
        delta_insights = 1 if action.action_type == ActionType.EXPLORATION else 0
        delta_files = 1

        return StateSnapshot(
            iteration=state.iteration + 1,
            metric_score=min(1.0, state.metric_score + delta_metric),
            test_coverage=min(1.0, state.test_coverage + delta_coverage),
            error_count=max(0, state.error_count + delta_errors),
            files_modified=state.files_modified + delta_files,
            insights_gained=state.insights_gained + delta_insights,
        )

    def get_statistics(self) -> dict:
        """Get reward function statistics."""
        if not self.trajectories:
            return {
                "total_transitions": 0,
                "avg_reward": 0.0,
                "success_rate": 0.0,
            }

        rewards = [t.reward for t in self.trajectories]
        successes = sum(1 for t in self.trajectories if t.outcome_success is True)
        total_with_outcome = sum(1 for t in self.trajectories if t.outcome_success is not None)

        return {
            "total_transitions": len(self.trajectories),
            "avg_reward": sum(rewards) / len(rewards),
            "max_reward": max(rewards),
            "min_reward": min(rewards),
            "success_rate": successes / total_with_outcome if total_with_outcome > 0 else 0.0,
            "weights": {
                "metric": self.weights.metric_improvement,
                "coverage": self.weights.coverage_improvement,
                "error_reduction": self.weights.error_reduction,
                "insight": self.weights.insight_generation,
                "exploration": self.weights.exploration_bonus,
                "efficiency": self.weights.efficiency_penalty,
            },
        }


class RewardGuidedAgent:
    """
    Agent that uses the reward function to guide decisions.
    """

    def __init__(self, reward_fn: RewardFunction):
        self.reward_fn = reward_fn
        self.current_state: Optional[StateSnapshot] = None

    def observe_state(self, state: StateSnapshot):
        """Update current state observation."""
        self.current_state = state

    def select_action(self, candidate_actions: list[Action]) -> Action:
        """Select the action with highest predicted reward."""
        if not self.current_state:
            return candidate_actions[0]

        ranked = self.reward_fn.get_best_actions(self.current_state, candidate_actions)
        return ranked[0][0]

    def execute_and_learn(self, action: Action, outcome_state: StateSnapshot,
                          success: Optional[bool] = None) -> float:
        """Execute action, record transition, and optionally learn from outcome."""
        if not self.current_state:
            return 0.0

        transition = self.reward_fn.record_transition(
            self.current_state, action, outcome_state, success
        )

        self.current_state = outcome_state
        return transition.reward


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    state_dir = Path(".ouroboros")
    state_dir.mkdir(exist_ok=True)

    reward_fn = RewardFunction(state_dir)

    # Create states
    state1 = StateSnapshot(
        iteration=1,
        metric_score=0.5,
        test_coverage=0.6,
        error_count=3,
        files_modified=2,
        insights_gained=1,
    )

    state2 = StateSnapshot(
        iteration=2,
        metric_score=0.55,
        test_coverage=0.65,
        error_count=2,
        files_modified=3,
        insights_gained=2,
    )

    # Create action
    action = Action(
        action_type=ActionType.CODE_CHANGE,
        description="Refactored core loop",
        target="src/ouroboros/core/loop.py",
    )

    # Compute reward
    reward = reward_fn.compute_reward(state1, action, state2)
    print(f"Reward: {reward:.4f}")

    # Record transition
    transition = reward_fn.record_transition(state1, action, state2, outcome_success=True)
    print(f"Recorded transition with reward: {transition.reward:.4f}")

    # Get statistics
    stats = reward_fn.get_statistics()
    print(f"\nStatistics: {json.dumps(stats, indent=2)}")

    # Rank candidate actions
    candidates = [
        Action(ActionType.CODE_CHANGE, "Fix bug in parser", "parser.py"),
        Action(ActionType.TEST_ADDITION, "Add unit tests", "tests/"),
        Action(ActionType.EXPLORATION, "Try new approach", "experimental/"),
        Action(ActionType.DOCUMENTATION, "Update docs", "README.md"),
    ]

    ranked = reward_fn.get_best_actions(state2, candidates)
    print("\nRanked actions:")
    for action, pred_reward in ranked:
        print(f"  {action.action_type.value}: {action.description} (predicted: {pred_reward:.4f})")
