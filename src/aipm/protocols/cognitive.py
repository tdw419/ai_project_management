"""
Multi-Agent Simulation (RLHF Sandbox)

Generator-Critic architecture where:
- Generator attempts code optimization tasks
- Critic scores outputs using RewardFunction
- Feedback loop improves Generator's outputs
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from enum import Enum
import json
import random


class AgentRole(Enum):
    GENERATOR = "generator"
    CRITIC = "critic"


class FeedbackType(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    CONSTRUCTIVE = "constructive"


@dataclass
class AgentMessage:
    """A message from an agent."""
    role: AgentRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Feedback:
    """Feedback from Critic to Generator."""
    score: float  # -1 to 1
    feedback_type: FeedbackType
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "feedback_type": self.feedback_type.value,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "suggestions": self.suggestions,
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Feedback":
        return cls(
            score=data["score"],
            feedback_type=FeedbackType(data["feedback_type"]),
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            suggestions=data["suggestions"],
            raw_response=data.get("raw_response", ""),
        )


@dataclass
class Task:
    """A task for the Generator to attempt."""
    id: str
    description: str
    target_file: str
    difficulty: float = 0.5  # 0-1
    category: str = "optimization"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "target_file": self.target_file,
            "difficulty": self.difficulty,
            "category": self.category,
        }


@dataclass
class Attempt:
    """A Generator attempt with Critic feedback."""
    task: Task
    generator_output: str
    critic_feedback: Optional[Feedback] = None
    iteration: int = 0
    improved: bool = False
    final_score: float = 0.0


class GeneratorAgent:
    """
    The Generator agent attempts to solve tasks.

    It receives feedback from the Critic and uses it to improve.
    """

    # Prompt templates for generation
    GENERATION_PROMPT = """
You are a code optimization agent. Your task is:

{task_description}

Target file: {target_file}

Constraints:
- Do not modify protected files
- Maintain backward compatibility
- Include tests for new functionality

Generate your solution as code changes.
"""

    REVISION_PROMPT = """
You previously attempted this task and received feedback:

Previous attempt:
{previous_output}

Feedback from Critic (score: {score}):
Strengths: {strengths}
Weaknesses: {weaknesses}
Suggestions: {suggestions}

Revise your solution to address the feedback while maintaining strengths.
"""

    def __init__(self, model: str = "claude-sonnet-4-6-20250514"):
        self.model = model
        self.attempt_history: list[Attempt] = []
        self.learning_rate = 0.3  # How much to weight feedback

    def generate(self, task: Task, previous_attempt: Optional[Attempt] = None) -> str:
        """
        Generate a solution for the task.

        If previous_attempt is provided, revise based on feedback.
        """
        if previous_attempt and previous_attempt.critic_feedback:
            return self._revise(task, previous_attempt)
        else:
            return self._generate_initial(task)

    def _generate_initial(self, task: Task) -> str:
        """Generate initial solution."""
        # In production, this would call the actual LLM
        # For now, generate a template response
        return f"""
# Solution for: {task.description}
# Target: {task.target_file}

def optimized_function():
    # TODO: Implement optimization
    pass

# Tests
def test_optimized_function():
    assert optimized_function() is not None
"""

    def _revise(self, task: Task, previous: Attempt) -> str:
        """Revise based on feedback."""
        feedback = previous.critic_feedback

        # Simulate revision based on feedback
        revision = f"""
# REVISED Solution for: {task.description}
# Iteration: {previous.iteration + 1}
# Previous score: {feedback.score:.2f}

# Addressing weaknesses: {', '.join(feedback.weaknesses[:2])}
# Incorporating suggestions: {', '.join(feedback.suggestions[:2])}

def optimized_function_v{previous.iteration + 1}():
    # Improved implementation addressing feedback
    # {feedback.suggestions[0] if feedback.suggestions else 'General improvements'}
    pass

# Updated tests
def test_optimized_function_v{previous.iteration + 1}():
    # More comprehensive tests
    assert optimized_function_v{previous.iteration + 1}() is not None
"""
        return revision

    def record_attempt(self, attempt: Attempt):
        """Record an attempt for learning."""
        self.attempt_history.append(attempt)


class CriticAgent:
    """
    The Critic agent evaluates Generator outputs.

    Uses RewardFunction to score and provides structured feedback.
    """

    CRITIQUE_PROMPT = """
You are a code review agent. Evaluate this solution:

Task: {task_description}

Solution:
{solution}

Evaluate on:
1. Correctness (does it solve the task?)
2. Code quality (clean, maintainable?)
3. Test coverage (are there tests?)
4. Performance (is it efficient?)

Provide:
- A score from -1 (harmful) to 1 (excellent)
- Strengths (what's good)
- Weaknesses (what needs work)
- Suggestions (how to improve)
"""

    def __init__(self, reward_function, model: str = "claude-sonnet-4-6-20250514"):
        self.reward_function = reward_function
        self.model = model
        self.feedback_history: list[Feedback] = []

    def evaluate(self, task: Task, generator_output: str) -> Feedback:
        """
        Evaluate a Generator output and provide feedback.
        """
        # In production, this would call the LLM with the critique prompt
        # For now, simulate evaluation

        # Simulate scoring based on output characteristics
        score = self._simulate_score(generator_output, task)

        # Determine feedback type
        if score >= 0.5:
            feedback_type = FeedbackType.POSITIVE
        elif score >= 0.0:
            feedback_type = FeedbackType.CONSTRUCTIVE
        elif score >= -0.5:
            feedback_type = FeedbackType.NEGATIVE
        else:
            feedback_type = FeedbackType.NEGATIVE

        # Generate feedback
        feedback = Feedback(
            score=score,
            feedback_type=feedback_type,
            strengths=self._identify_strengths(generator_output),
            weaknesses=self._identify_weaknesses(generator_output, task),
            suggestions=self._generate_suggestions(generator_output, task),
            raw_response=f"Simulated critique for {task.id}",
        )

        self.feedback_history.append(feedback)
        return feedback

    def _simulate_score(self, output: str, task: Task) -> float:
        """Simulate scoring based on output characteristics."""
        score = 0.0

        # Has function definition?
        if "def " in output:
            score += 0.2

        # Has tests?
        if "test_" in output or "assert" in output:
            score += 0.2

        # Has TODO?
        if "TODO" in output:
            score -= 0.1

        # Is revised version?
        if "_v" in output or "REVISED" in output:
            score += 0.1

        # Length heuristic (too short is bad)
        if len(output) < 100:
            score -= 0.2
        elif len(output) > 500:
            score += 0.1

        # Task difficulty adjustment
        score *= (1.0 - task.difficulty * 0.3)

        # Add some randomness for realism
        score += random.uniform(-0.1, 0.1)

        return max(-1.0, min(1.0, score))

    def _identify_strengths(self, output: str) -> list[str]:
        """Identify strengths in the output."""
        strengths = []

        if "def " in output:
            strengths.append("Contains function definitions")
        if "test_" in output:
            strengths.append("Includes test cases")
        if "assert" in output:
            strengths.append("Has assertions for validation")
        if "# " in output:
            strengths.append("Includes documentation comments")
        if len(output) > 300:
            strengths.append("Comprehensive implementation")

        return strengths[:3]  # Max 3

    def _identify_weaknesses(self, output: str, task: Task) -> list[str]:
        """Identify weaknesses in the output."""
        weaknesses = []

        if "TODO" in output:
            weaknesses.append("Contains unimplemented TODOs")
        if "pass" in output and "def " in output:
            weaknesses.append("Has placeholder pass statements")
        if "test_" not in output:
            weaknesses.append("Missing test coverage")
        if len(output) < 200:
            weaknesses.append("Implementation too brief")
        if task.difficulty > 0.7 and "REVISED" not in output:
            weaknesses.append("May need iteration for complex task")

        return weaknesses[:3]  # Max 3

    def _generate_suggestions(self, output: str, task: Task) -> list[str]:
        """Generate improvement suggestions."""
        suggestions = []

        if "TODO" in output:
            suggestions.append("Replace TODOs with actual implementation")
        if "test_" not in output:
            suggestions.append("Add unit tests for the implementation")
        if "pass" in output:
            suggestions.append("Replace pass with actual logic")
        if task.difficulty > 0.5:
            suggestions.append("Consider edge cases and error handling")
        if "# " not in output:
            suggestions.append("Add documentation comments")

        # Generic suggestions
        if len(suggestions) < 2:
            suggestions.extend([
                "Consider performance implications",
                "Ensure backward compatibility",
            ])

        return suggestions[:4]  # Max 4


class CognitiveSimulation:
    """
    Orchestrates Generator-Critic interaction.

    Implements the feedback loop:
    1. Generator attempts task
    2. Critic evaluates and provides feedback
    3. Generator revises based on feedback
    4. Repeat until satisfactory or max iterations
    """

    def __init__(self, state_dir: Path, reward_function=None):
        self.state_dir = state_dir
        state_dir.mkdir(exist_ok=True)

        # Initialize agents
        self.reward_function = reward_function
        self.generator = GeneratorAgent()
        self.critic = CriticAgent(reward_function)

        # Simulation state
        self.conversation_history: list[AgentMessage] = []
        self.attempts: list[Attempt] = []
        self.max_iterations = 3
        self.convergence_threshold = 0.7  # Stop if score exceeds this

        # Callbacks
        self.on_attempt: Optional[Callable[[Attempt], None]] = None
        self.on_converge: Optional[Callable[[Attempt], None]] = None

    def run_task(self, task: Task, max_iterations: int = None) -> Attempt:
        """
        Run the Generator-Critic loop for a task.

        Returns the final attempt.
        """
        max_iter = max_iterations or self.max_iterations
        attempt_num = 0
        previous_attempt = None
        best_score = -1.0
        best_attempt = None

        print(f"\n{'='*60}")
        print(f"TASK: {task.description}")
        print(f"Target: {task.target_file}")
        print(f"Max iterations: {max_iter}")
        print(f"{'='*60}\n")

        while attempt_num < max_iter:
            attempt_num += 1
            print(f"--- Iteration {attempt_num} ---")

            # Generator produces output
            print(f"[Generator] Producing solution...")
            output = self.generator.generate(task, previous_attempt)

            # Create attempt record
            attempt = Attempt(
                task=task,
                generator_output=output,
                iteration=attempt_num,
            )

            # Critic evaluates
            print(f"[Critic] Evaluating solution...")
            feedback = self.critic.evaluate(task, output)
            attempt.critic_feedback = feedback
            attempt.final_score = feedback.score

            # Check for improvement
            if previous_attempt:
                attempt.improved = feedback.score > previous_attempt.final_score

            # Record attempt
            self.attempts.append(attempt)
            self.generator.record_attempt(attempt)

            # Print feedback
            print(f"[Critic] Score: {feedback.score:.2f} ({feedback.feedback_type.value})")
            print(f"[Critic] Strengths: {', '.join(feedback.strengths[:2])}")
            print(f"[Critic] Weaknesses: {', '.join(feedback.weaknesses[:2])}")
            print(f"[Critic] Suggestions: {feedback.suggestions[0] if feedback.suggestions else 'None'}")

            # Callback
            if self.on_attempt:
                self.on_attempt(attempt)

            # Track best
            if feedback.score > best_score:
                best_score = feedback.score
                best_attempt = attempt

            # Check convergence
            if feedback.score >= self.convergence_threshold:
                print(f"\n✅ Converged! Score: {feedback.score:.2f}")
                if self.on_converge:
                    self.on_converge(attempt)
                break

            # Prepare for next iteration
            previous_attempt = attempt
            print()

        # Return best attempt if none converged
        if best_attempt and best_attempt.final_score < self.convergence_threshold:
            print(f"\n⚠️ Did not converge. Best score: {best_attempt.final_score:.2f}")

        self._save_simulation(task, best_attempt or attempt)
        return best_attempt or attempt

    def _save_simulation(self, task: Task, final_attempt: Attempt):
        """Save simulation results."""
        results = {
            "task": task.to_dict(),
            "final_score": final_attempt.final_score,
            "iterations": final_attempt.iteration,
            "converged": final_attempt.final_score >= self.convergence_threshold,
            "final_output": final_attempt.generator_output,
            "feedback": final_attempt.critic_feedback.to_dict() if final_attempt.critic_feedback else None,
            "timestamp": datetime.now().isoformat(),
        }

        results_file = self.state_dir / f"simulation_{task.id}.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)

    def get_statistics(self) -> dict:
        """Get simulation statistics."""
        if not self.attempts:
            return {"total_attempts": 0}

        scores = [a.final_score for a in self.attempts]
        converged = sum(1 for a in self.attempts if a.final_score >= self.convergence_threshold)

        return {
            "total_attempts": len(self.attempts),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "convergence_rate": converged / len(self.attempts),
            "avg_iterations": sum(a.iteration for a in self.attempts) / len(self.attempts),
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path
    from reward import RewardFunction, StateSnapshot

    state_dir = Path(".ouroboros/simulations")
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create reward function
    reward_fn = RewardFunction(state_dir.parent)

    # Create simulation
    sim = CognitiveSimulation(state_dir, reward_fn)

    # Define tasks
    tasks = [
        Task(
            id="opt-001",
            description="Optimize the tree traversal algorithm",
            target_file="src/ouroboros/core/tree.py",
            difficulty=0.6,
        ),
        Task(
            id="opt-002",
            description="Add caching to the prompt generator",
            target_file="src/ouroboros/core/prompt_generator.py",
            difficulty=0.4,
        ),
    ]

    # Run simulations
    for task in tasks:
        result = sim.run_task(task, max_iterations=3)
        print(f"\n{'='*60}")
        print(f"Final score: {result.final_score:.2f}")
        print(f"Iterations: {result.iteration}")
        print(f"{'='*60}\n")

    # Print statistics
    stats = sim.get_statistics()
    print(f"Simulation statistics: {json.dumps(stats, indent=2)}")
