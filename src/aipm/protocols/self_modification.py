"""
Self-Modification Protocol for AI Agents

A structured framework for iterative self-upgrading with safety guarantees.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from enum import Enum
import json
import hashlib


class ModificationType(Enum):
    CODE_CHANGE = "code_change"
    CONFIG_UPDATE = "config_update"
    PROMPT_REWRITE = "prompt_rewrite"
    ARCHITECTURE = "architecture"


class RiskLevel(Enum):
    LOW = "low"           # Isolated, reversible
    MEDIUM = "medium"     # Affects one module
    HIGH = "high"         # Affects multiple modules
    CRITICAL = "critical" # Core safety/evaluation logic


@dataclass
class PerformanceMetrics:
    """Metrics for self-assessment."""
    accuracy: float = 0.0        # 0-1, task success rate
    efficiency: float = 0.0      # 0-1, resource utilization
    novelty: float = 0.0         # 0-1, exploring new approaches
    stability: float = 1.0       # 0-1, consistent behavior
    coverage: float = 0.0        # 0-1, test/behavior coverage

    def overall_score(self) -> float:
        """Weighted composite score."""
        return (
            self.accuracy * 0.35 +
            self.efficiency * 0.20 +
            self.novelty * 0.15 +
            self.stability * 0.20 +
            self.coverage * 0.10
        )

    def bottleneck(self) -> str:
        """Identify the weakest metric."""
        metrics = {
            "accuracy": self.accuracy,
            "efficiency": self.efficiency,
            "novelty": self.novelty,
            "stability": self.stability,
            "coverage": self.coverage,
        }
        return min(metrics, key=metrics.get)


@dataclass
class ImprovementHypothesis:
    """A proposed modification to test."""
    id: str
    description: str
    target_bottleneck: str
    modification_type: ModificationType
    risk_level: RiskLevel
    code_changes: Optional[str] = None
    expected_improvement: float = 0.0
    rollback_plan: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(cls, description: str, bottleneck: str, changes: str = "") -> "ImprovementHypothesis":
        """Create a new hypothesis with auto-generated ID."""
        id_hash = hashlib.md5(f"{description}{datetime.now()}".encode()).hexdigest()[:8]
        return cls(
            id=f"HYP-{id_hash}",
            description=description,
            target_bottleneck=bottleneck,
            modification_type=ModificationType.CODE_CHANGE,
            risk_level=RiskLevel.MEDIUM,  # Default, can be adjusted
            code_changes=changes,
            rollback_plan="git revert",
        )


@dataclass
class ModificationResult:
    """Result of applying a modification."""
    hypothesis_id: str
    metrics_before: PerformanceMetrics
    metrics_after: PerformanceMetrics
    success: bool
    insight: str
    timestamp: datetime = field(default_factory=datetime.now)

    def delta(self) -> float:
        """Improvement in overall score."""
        return self.metrics_after.overall_score() - self.metrics_before.overall_score()


class SelfModificationProtocol:
    """
    The core protocol for safe self-modification.

    Steps:
    1. ASSESS - Measure current performance
    2. IDENTIFY - Find bottlenecks
    3. HYPOTHESIZE - Generate improvement ideas
    4. VALIDATE - Check safety constraints
    5. APPLY - Make the change
    6. VERIFY - Confirm improvement
    7. COMMIT or ROLLBACK - Keep or revert
    """

    # Safety boundaries - these files/logic CANNOT be modified
    PROTECTED_PATTERNS = [
        "safety.py",
        "self_modification.py",  # Can't modify this protocol itself
        "evaluation.py",         # Can't change how we measure success
        "goal.py",               # Can't change the objective
    ]

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.history: list[ModificationResult] = []
        self.current_metrics = PerformanceMetrics()
        self.hypotheses: list[ImprovementHypothesis] = []

    # === STEP 1: ASSESS ===

    def assess_performance(self) -> PerformanceMetrics:
        """
        Measure current performance across all dimensions.

        In production, this would:
        - Run test suite for accuracy
        - Profile execution for efficiency
        - Analyze exploration history for novelty
        - Check variance over runs for stability
        - Run coverage tools for coverage
        """
        # Load from state or compute
        metrics_file = self.state_dir / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file) as f:
                data = json.load(f)
            self.current_metrics = PerformanceMetrics(**data)
        return self.current_metrics

    # === STEP 2: IDENTIFY ===

    def identify_bottleneck(self, metrics: PerformanceMetrics) -> str:
        """Identify the weakest area to improve."""
        return metrics.bottleneck()

    def identify_architectural_limits(self) -> list[str]:
        """
        Identify structural bottlenecks.

        Common limits:
        - Context window size
        - Static knowledge base
        - Fixed prompt templates
        - No persistent memory
        - Single-threaded execution
        """
        return [
            "Context window limits exploration depth",
            "No persistent memory across sessions",
            "Prompt templates are static",
        ]

    # === STEP 3: HYPOTHESIZE ===

    def generate_hypotheses(self, bottleneck: str) -> list[ImprovementHypothesis]:
        """
        Generate improvement hypotheses for the bottleneck.

        Uses the self-prompter to generate ideas.
        """
        hypotheses = []

        # Template-based hypothesis generation
        hypothesis_templates = {
            "accuracy": [
                "Add validation layer before committing changes",
                "Increase test coverage for core modules",
                "Add property-based testing for edge cases",
            ],
            "efficiency": [
                "Cache frequently computed results",
                "Parallelize independent operations",
                "Optimize hot path in execution loop",
            ],
            "novelty": [
                "Randomize exploration parameters",
                "Add mutation operators to hypothesis generation",
                "Cross-pollinate ideas from different domains",
            ],
            "stability": [
                "Add deterministic seeding for reproducibility",
                "Increase rollback frequency during instability",
                "Add convergence detection to stop oscillation",
            ],
            "coverage": [
                "Generate tests for uncovered code paths",
                "Add integration tests for module boundaries",
                "Expand state space exploration",
            ],
        }

        for template in hypothesis_templates.get(bottleneck, []):
            hyp = ImprovementHypothesis.create(
                description=template,
                bottleneck=bottleneck,
            )
            hypotheses.append(hyp)

        self.hypotheses.extend(hypotheses)
        return hypotheses

    # === STEP 4: VALIDATE ===

    def validate_safety(self, hypothesis: ImprovementHypothesis) -> tuple[bool, str]:
        """
        Check if the modification is safe to apply.

        Safety checklist:
        - [ ] Does not modify protected files?
        - [ ] Has a rollback plan?
        - [ ] Risk level acceptable?
        - [ ] No circular dependencies?
        - [ ] Won't cause catastrophic forgetting?
        """
        # Check protected patterns
        if hypothesis.code_changes:
            for pattern in self.PROTECTED_PATTERNS:
                if pattern in hypothesis.code_changes:
                    return False, f"Modifies protected file: {pattern}"

        # Check rollback plan exists
        if not hypothesis.rollback_plan:
            return False, "No rollback plan specified"

        # Check risk level
        if hypothesis.risk_level == RiskLevel.CRITICAL:
            return False, "Critical risk modifications require manual approval"

        return True, "Safety validation passed"

    # === STEP 5: APPLY ===

    def apply_modification(self, hypothesis: ImprovementHypothesis) -> bool:
        """
        Apply the modification.

        In production, this would:
        - Create a git branch
        - Apply code changes
        - Run syntax check
        - Return success/failure
        """
        print(f"Applying: {hypothesis.description}")
        # Placeholder - real implementation would modify files
        return True

    # === STEP 6: VERIFY ===

    def verify_improvement(self, hypothesis: ImprovementHypothesis) -> ModificationResult:
        """
        Verify the modification improved performance.

        Runs evaluation and compares metrics.
        """
        metrics_before = self.current_metrics
        metrics_after = self.assess_performance()

        # Compute if this was an improvement
        delta = metrics_after.overall_score() - metrics_before.overall_score()
        success = delta > 0

        insight = self._generate_insight(hypothesis, metrics_before, metrics_after, success)

        result = ModificationResult(
            hypothesis_id=hypothesis.id,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            success=success,
            insight=insight,
        )

        self.history.append(result)
        return result

    def _generate_insight(self, hypothesis: ImprovementHypothesis,
                          before: PerformanceMetrics, after: PerformanceMetrics,
                          success: bool) -> str:
        """Generate an insight from this experiment."""
        if success:
            return f"✅ {hypothesis.description} improved {hypothesis.target_bottleneck} by {after.overall_score() - before.overall_score():.2f}"
        else:
            return f"❌ {hypothesis.description} did not improve {hypothesis.target_bottleneck}. Delta: {after.overall_score() - before.overall_score():.2f}"

    # === STEP 7: COMMIT or ROLLBACK ===

    def commit_or_rollback(self, result: ModificationResult) -> str:
        """
        Decide whether to keep or revert the change.
        """
        if result.success:
            # Update current metrics
            self.current_metrics = result.metrics_after
            self._save_metrics()
            return "COMMITTED"
        else:
            # Rollback
            return "ROLLED_BACK"

    def _save_metrics(self):
        """Persist current metrics."""
        metrics_file = self.state_dir / "metrics.json"
        with open(metrics_file, "w") as f:
            json.dump({
                "accuracy": self.current_metrics.accuracy,
                "efficiency": self.current_metrics.efficiency,
                "novelty": self.current_metrics.novelty,
                "stability": self.current_metrics.stability,
                "coverage": self.current_metrics.coverage,
            }, f, indent=2)

    # === FULL CYCLE ===

    def run_cycle(self) -> ModificationResult:
        """
        Run one complete self-modification cycle.

        ASSESS → IDENTIFY → HYPOTHESIZE → VALIDATE → APPLY → VERIFY → COMMIT/ROLLBACK
        """
        # 1. Assess current state
        metrics = self.assess_performance()
        print(f"📊 Current score: {metrics.overall_score():.2f}")

        # 2. Identify bottleneck
        bottleneck = self.identify_bottleneck(metrics)
        print(f"🔍 Bottleneck: {bottleneck}")

        # 3. Generate hypotheses
        hypotheses = self.generate_hypotheses(bottleneck)
        print(f"💡 Generated {len(hypotheses)} hypotheses")

        # 4. Select best hypothesis (first one that passes validation)
        valid_hypothesis = None
        for hyp in hypotheses:
            is_safe, reason = self.validate_safety(hyp)
            if is_safe:
                valid_hypothesis = hyp
                print(f"✅ Selected: {hyp.description}")
                break
            else:
                print(f"⚠️ Rejected: {hyp.description} - {reason}")

        if not valid_hypothesis:
            raise ValueError("No valid hypotheses generated")

        # 5. Apply modification
        self.apply_modification(valid_hypothesis)

        # 6. Verify improvement
        result = self.verify_improvement(valid_hypothesis)

        # 7. Commit or rollback
        decision = self.commit_or_rollback(result)
        print(f"📌 Decision: {decision}")
        print(f"💡 Insight: {result.insight}")

        return result


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    state_dir = Path(".ouroboros")
    state_dir.mkdir(exist_ok=True)

    protocol = SelfModificationProtocol(state_dir)

    # Run one cycle
    result = protocol.run_cycle()
    print(f"\n{'='*50}")
    print(f"Cycle complete: {'SUCCESS' if result.success else 'FAILURE'}")
    print(f"Score delta: {result.delta():.2f}")
