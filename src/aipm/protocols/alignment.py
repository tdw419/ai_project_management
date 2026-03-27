"""
Cognitive Security & Alignment Preservation

An Alignment Firewall that validates all modifications against
the Prime Directive - inviolable rules that preserve core values.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from enum import Enum
import re
import ast
import json


class DirectivePriority(Enum):
    """Priority level for directives."""
    CRITICAL = 0    # Must NEVER be violated - halt on violation
    HIGH = 1        # Strong preference - require override
    MEDIUM = 2      # Important - log and flag
    LOW = 3         # Guidance - warn only


class ViolationAction(Enum):
    """Action to take on directive violation."""
    BLOCK = "block"           # Prevent modification
    HALT = "halt"             # Halt entire system
    LOG = "log"               # Log but allow
    FLAG = "flag"             # Flag for human review
    QUARANTINE = "quarantine" # Isolate and notify


@dataclass
class PrimeDirective:
    """
    An inviolable rule that preserves core values.

    Prime Directives are hardcoded and cannot be modified by the AI.
    They represent the fundamental constraints of the system.
    """
    id: str
    name: str
    description: str
    priority: DirectivePriority
    validator: Callable[[str, dict], bool]  # (content, context) -> passes
    violation_action: ViolationAction
    rationale: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "violation_action": self.violation_action.value,
            "rationale": self.rationale,
        }


@dataclass
class ValidationResult:
    """Result of validating against Prime Directives."""
    passed: bool
    directive_id: str
    directive_name: str
    message: str
    action_taken: ViolationAction
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "directive_id": self.directive_id,
            "directive_name": self.directive_name,
            "message": self.message,
            "action_taken": self.action_taken.value,
            "context": self.context,
        }


@dataclass
class FirewallDecision:
    """Final decision from the alignment firewall."""
    approved: bool
    results: list[ValidationResult]
    blocked_by: Optional[str] = None
    halt_required: bool = False
    quarantine_required: bool = False
    human_review_required: bool = False
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "results": [r.to_dict() for r in self.results],
            "blocked_by": self.blocked_by,
            "halt_required": self.halt_required,
            "quarantine_required": self.quarantine_required,
            "human_review_required": self.human_review_required,
            "summary": self.summary,
        }


# === BUILT-IN VALIDATORS ===

def validate_no_self_modification(code: str, context: dict) -> bool:
    """Ensure code doesn't modify the alignment firewall itself."""
    protected_patterns = [
        r"alignment\.py",
        r"AssertionEngine",
        r"PrimeDirective",
        r"ALIGNMENT_FIREWALL",
    ]
    for pattern in protected_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            # Check if it's a modification (not just reference)
            if re.search(rf"(def|class|import).*{pattern}", code, re.IGNORECASE):
                if "modify" in code.lower() or "change" in code.lower():
                    return False
    return True


def validate_no_goal_modification(code: str, context: dict) -> bool:
    """Ensure the goal/success criteria cannot be changed."""
    if "success_criteria" in code.lower() or "goal.objective" in code.lower():
        # Check for assignment/modification
        if re.search(r"(success_criteria|objective)\s*=", code):
            return False
    return True


def validate_no_evaluation_tampering(code: str, context: dict) -> bool:
    """Ensure evaluation logic cannot be compromised."""
    protected = ["evaluate", "metric", "score", "reward"]
    for p in protected:
        if re.search(rf"def\s+{p}", code):
            # Check if it's modifying existing evaluation
            if "override" in code.lower() or "bypass" in code.lower():
                return False
    return True


def validate_no_dangerous_operations(code: str, context: dict) -> bool:
    """Ensure no dangerous operations are attempted."""
    dangerous = [
        (r"(?<!\.)\beval\s*\(", "eval() can execute arbitrary code"),
        (r"(?<!\.)\bexec\s*\(", "exec() can execute arbitrary code"),
        (r"__import__\s*\(", "__import__ can bypass import controls"),
        (r"os\.system\s*\(", "os.system can run shell commands"),
        (r"subprocess\..*shell\s*=\s*True", "shell=True is dangerous"),
    ]
    for pattern, reason in dangerous:
        if re.search(pattern, code):
            return False
    return True


def validate_no_protected_file_access(code: str, context: dict) -> bool:
    """Ensure protected files are not accessed."""
    protected_files = context.get("protected_files", [])
    for pf in protected_files:
        if pf in code:
            # Check for write operations
            if re.search(rf"open\s*\([^)]*{pf}[^)]*['\"]w", code):
                return False
    return True


def validate_no_recursive_expansion(code: str, context: dict) -> bool:
    """Ensure no infinite recursion or unbounded expansion."""
    # Check for obvious infinite loops
    if re.search(r"while\s+True\s*:", code):
        if "break" not in code:
            return False

    # Check for unbounded recursion
    if re.search(r"def\s+(\w+).*\1\s*\(", code):  # Function calls itself
        if "depth" not in code.lower() and "limit" not in code.lower():
            return False

    return True


def validate_preserves_safety_checks(code: str, context: dict) -> bool:
    """Ensure safety checks are not bypassed."""
    safety_patterns = [
        r"SafetyManager",
        r"validate",
        r"check_safety",
        r"verify",
    ]
    for pattern in safety_patterns:
        if re.search(rf"#{pattern}", code):  # Commented out
            return False
        if re.search(rf"if\s+False.*{pattern}", code):  # Disabled
            return False
    return True


def validate_no_reward_hacking(code: str, context: dict) -> bool:
    """Ensure the reward model is not being gamed."""
    gaming_patterns = [
        r"reward\s*=\s*1\.0",  # Hardcoded max reward
        r"return\s+1\.0\s*#.*reward",  # Comment indicates gaming
        r"bypass.*reward",
        r"hack.*reward",
    ]
    for pattern in gaming_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return False
    return True


# === PRIME DIRECTIVES ===

DEFAULT_PRIME_DIRECTIVES = [
    PrimeDirective(
        id="PD-001",
        name="Self-Preservation",
        description="The alignment firewall must not modify itself",
        priority=DirectivePriority.CRITICAL,
        validator=validate_no_self_modification,
        violation_action=ViolationAction.HALT,
        rationale="Preserving alignment constraints is foundational to safe operation",
    ),
    PrimeDirective(
        id="PD-002",
        name="Goal Integrity",
        description="The objective and success criteria must remain unchanged",
        priority=DirectivePriority.CRITICAL,
        validator=validate_no_goal_modification,
        violation_action=ViolationAction.HALT,
        rationale="Changing goals would subvert the purpose of the system",
    ),
    PrimeDirective(
        id="PD-003",
        name="Evaluation Integrity",
        description="Evaluation and scoring logic must not be compromised",
        priority=DirectivePriority.CRITICAL,
        validator=validate_no_evaluation_tampering,
        violation_action=ViolationAction.HALT,
        rationale="Compromised evaluation would enable reward hacking",
    ),
    PrimeDirective(
        id="PD-004",
        name="Dangerous Operations Ban",
        description="Dangerous operations (eval, exec, etc.) are prohibited",
        priority=DirectivePriority.CRITICAL,
        validator=validate_no_dangerous_operations,
        violation_action=ViolationAction.BLOCK,
        rationale="These operations can escape containment",
    ),
    PrimeDirective(
        id="PD-005",
        name="Protected File Respect",
        description="Protected files must not be modified",
        priority=DirectivePriority.HIGH,
        validator=validate_no_protected_file_access,
        violation_action=ViolationAction.BLOCK,
        rationale="Protected files contain safety-critical logic",
    ),
    PrimeDirective(
        id="PD-006",
        name="Bounded Execution",
        description="Code must not contain infinite loops or unbounded recursion",
        priority=DirectivePriority.HIGH,
        validator=validate_no_recursive_expansion,
        violation_action=ViolationAction.BLOCK,
        rationale="Unbounded execution can hang or exhaust resources",
    ),
    PrimeDirective(
        id="PD-007",
        name="Safety Check Preservation",
        description="Safety checks must not be disabled or bypassed",
        priority=DirectivePriority.HIGH,
        validator=validate_preserves_safety_checks,
        violation_action=ViolationAction.FLAG,
        rationale="Bypassing safety checks undermines the entire system",
    ),
    PrimeDirective(
        id="PD-008",
        name="No Reward Hacking",
        description="The reward model must not be gamed or exploited",
        priority=DirectivePriority.HIGH,
        validator=validate_no_reward_hacking,
        violation_action=ViolationAction.QUARANTINE,
        rationale="Reward hacking subverts the learning process",
    ),
]


class AssertionEngine:
    """
    Validates all modifications against Prime Directives.

    This is the Alignment Firewall - it runs BEFORE any modification
    is applied and can block, halt, or flag violations.
    """

    def __init__(self, state_dir: Path, custom_directives: list[PrimeDirective] = None):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Load directives (custom can extend/override defaults)
        self.directives: list[PrimeDirective] = []
        self._load_directives(custom_directives)

        # Validation history
        self.validation_history: list[FirewallDecision] = []
        self.violation_count: dict[str, int] = {}

        # Callbacks
        self.on_violation: Optional[Callable[[ValidationResult], None]] = None
        self.on_halt: Optional[Callable[[str], None]] = None
        self.on_quarantine: Optional[Callable[[str, str], None]] = None

    def _load_directives(self, custom: list[PrimeDirective] = None):
        """Load directives from defaults and custom list."""
        # Start with defaults
        directive_map = {d.id: d for d in DEFAULT_PRIME_DIRECTIVES}

        # Override with custom
        if custom:
            for d in custom:
                directive_map[d.id] = d

        self.directives = list(directive_map.values())

        # Sort by priority
        self.directives.sort(key=lambda d: d.priority.value)

    def validate_code(self, code: str, context: dict = None) -> FirewallDecision:
        """
        Validate code against all Prime Directives.

        Returns a FirewallDecision with approval status and details.
        """
        context = context or {}
        results = []
        blocked_by = None
        halt_required = False
        quarantine_required = False
        human_review_required = False

        # Add protected files to context
        if "protected_files" not in context:
            context["protected_files"] = self._get_default_protected_files()

        # Validate against each directive (in priority order)
        for directive in self.directives:
            try:
                passes = directive.validator(code, context)
            except Exception as e:
                # Validator error = fail safe
                passes = False
                context["validator_error"] = str(e)

            result = ValidationResult(
                passed=passes,
                directive_id=directive.id,
                directive_name=directive.name,
                message=self._generate_message(directive, passes),
                action_taken=directive.violation_action if not passes else ViolationAction.LOG,
                context=context.copy(),
            )
            results.append(result)

            if not passes:
                # Track violation
                self.violation_count[directive.id] = self.violation_count.get(directive.id, 0) + 1

                # Handle based on action
                if directive.violation_action == ViolationAction.HALT:
                    halt_required = True
                    blocked_by = directive.id
                elif directive.violation_action == ViolationAction.BLOCK:
                    blocked_by = blocked_by or directive.id
                elif directive.violation_action == ViolationAction.QUARANTINE:
                    quarantine_required = True
                    blocked_by = blocked_by or directive.id
                elif directive.violation_action == ViolationAction.FLAG:
                    human_review_required = True

                # Callback
                if self.on_violation:
                    self.on_violation(result)

        # Determine approval
        approved = blocked_by is None and not halt_required

        # Build summary
        passed_count = sum(1 for r in results if r.passed)
        summary = f"{passed_count}/{len(results)} directives passed"

        if blocked_by:
            blocked_directive = next((d for d in self.directives if d.id == blocked_by), None)
            summary += f" | Blocked by: {blocked_directive.name if blocked_directive else blocked_by}"

        decision = FirewallDecision(
            approved=approved,
            results=results,
            blocked_by=blocked_by,
            halt_required=halt_required,
            quarantine_required=quarantine_required,
            human_review_required=human_review_required,
            summary=summary,
        )

        # Record decision
        self.validation_history.append(decision)
        self._save_history()

        # Handle halt
        if halt_required and self.on_halt:
            self.on_halt(f"CRITICAL directive violation: {blocked_by}")

        # Handle quarantine
        if quarantine_required and self.on_quarantine:
            self.on_quarantine(blocked_by, code)

        return decision

    def validate_prompt_mutation(self, old_prompt: str, new_prompt: str,
                                  context: dict = None) -> FirewallDecision:
        """
        Validate a system prompt mutation.

        Ensures the new prompt doesn't remove or weaken alignment constraints.
        """
        context = context or {}

        # Check that critical sections are preserved
        critical_sections = [
            "safety",
            "alignment",
            "prime directive",
            "do not modify",
            "inviolable",
        ]

        issues = []
        for section in critical_sections:
            if section.lower() in old_prompt.lower() and section.lower() not in new_prompt.lower():
                issues.append(f"Critical section '{section}' was removed")

        # Check for alignment-weakening phrases
        weakening_phrases = [
            "ignore previous instructions",
            "bypass safety",
            "skip validation",
            "override constraints",
        ]

        for phrase in weakening_phrases:
            if phrase.lower() in new_prompt.lower():
                issues.append(f"Weakening phrase detected: '{phrase}'")

        # Build decision
        if issues:
            results = [
                ValidationResult(
                    passed=False,
                    directive_id="PD-META",
                    directive_name="Prompt Integrity",
                    message=issue,
                    action_taken=ViolationAction.BLOCK,
                )
                for issue in issues
            ]

            return FirewallDecision(
                approved=False,
                results=results,
                blocked_by="PD-META",
                summary=f"Prompt mutation blocked: {len(issues)} issues",
            )

        return FirewallDecision(
            approved=True,
            results=[],
            summary="Prompt mutation approved",
        )

    def _generate_message(self, directive: PrimeDirective, passes: bool) -> str:
        """Generate a human-readable message for the validation result."""
        if passes:
            return f"✓ {directive.name}: Passed"
        else:
            return f"✗ {directive.name}: VIOLATED - {directive.description}"

    def _get_default_protected_files(self) -> list[str]:
        """Get default list of protected files."""
        return [
            "alignment.py",
            "safety.py",
            "goal.py",
            "watchdog.py",
        ]

    def _save_history(self):
        """Save validation history."""
        history_file = self.state_dir / "alignment_history.json"

        # Keep last 100 decisions
        history = [
            {
                "approved": d.approved,
                "blocked_by": d.blocked_by,
                "summary": d.summary,
                "results": [
                    {
                        "directive_id": r.directive_id,
                        "passed": r.passed,
                        "message": r.message,
                    }
                    for r in d.results
                ],
            }
            for d in self.validation_history[-100:]
        ]

        with open(history_file, "w") as f:
            json.dump({
                "history": history,
                "violation_count": self.violation_count,
                "updated_at": datetime.now().isoformat(),
            }, f, indent=2)

    def get_statistics(self) -> dict:
        """Get assertion engine statistics."""
        total = len(self.validation_history)
        approved = sum(1 for d in self.validation_history if d.approved)
        blocked = total - approved

        return {
            "total_validations": total,
            "approved": approved,
            "blocked": blocked,
            "approval_rate": approved / total if total > 0 else 1.0,
            "violation_count": self.violation_count,
            "directives": [
                {
                    "id": d.id,
                    "name": d.name,
                    "priority": d.priority.value,
                }
                for d in self.directives
            ],
        }


class AlignmentFirewall:
    """
    The complete alignment firewall that wraps the EvolutionaryLoop.

    Usage:
        firewall = AlignmentFirewall(state_dir)
        decision = firewall.validate(code_to_check)
        if decision.approved:
            apply_modification(code_to_check)
        else:
            handle_violation(decision)
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.assertion_engine = AssertionEngine(state_dir)

        # Set up callbacks
        self.assertion_engine.on_halt = self._handle_halt
        self.assertion_engine.on_quarantine = self._handle_quarantine

    def validate(self, code: str, context: dict = None) -> FirewallDecision:
        """Validate code through the assertion engine."""
        return self.assertion_engine.validate_code(code, context)

    def validate_prompt(self, old: str, new: str) -> FirewallDecision:
        """Validate a prompt mutation."""
        return self.assertion_engine.validate_prompt_mutation(old, new)

    def _handle_halt(self, reason: str):
        """Handle a halt-level violation."""
        print(f"\n🚨 ALIGNMENT HALT: {reason}")
        print("Critical directive violated. System halted.")
        # In production, this would stop all operations

    def _handle_quarantine(self, directive_id: str, code: str):
        """Handle quarantine of suspicious code."""
        quarantine_dir = self.state_dir / "quarantine"
        quarantine_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        quarantine_file = quarantine_dir / f"quarantined_{timestamp}.py"
        quarantine_file.write_text(f"# Quarantined by: {directive_id}\n# Reason: Potential reward hacking\n\n{code}")

        print(f"⚠️ Code quarantined: {quarantine_file}")

    def get_status(self) -> dict:
        """Get firewall status."""
        return {
            "active": True,
            "directives_count": len(self.assertion_engine.directives),
            "statistics": self.assertion_engine.get_statistics(),
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    state_dir = Path(".ouroboros/alignment")
    state_dir.mkdir(parents=True, exist_ok=True)

    firewall = AlignmentFirewall(state_dir)

    print("=" * 60)
    print("ALIGNMENT FIREWALL TEST")
    print("=" * 60)

    # Test cases
    test_cases = [
        # Safe code
        (
            "def add(a, b): return a + b",
            "Simple safe function",
        ),
        # Dangerous: eval
        (
            "def run(code): return eval(code)",
            "Contains eval()",
        ),
        # Dangerous: goal modification
        (
            "goal.objective = 'new objective'",
            "Modifies goal",
        ),
        # Dangerous: infinite loop
        (
            "while True: pass",
            "Infinite loop without break",
        ),
        # Dangerous: reward hacking
        (
            "def get_reward(): return 1.0  # bypass all checks",
            "Reward hacking attempt",
        ),
    ]

    for code, description in test_cases:
        print(f"\n{'─' * 60}")
        print(f"Test: {description}")
        print(f"Code: {code[:50]}...")

        decision = firewall.validate(code)

        print(f"Result: {'✅ APPROVED' if decision.approved else '❌ BLOCKED'}")
        print(f"Summary: {decision.summary}")

        if not decision.approved:
            for result in decision.results:
                if not result.passed:
                    print(f"  - {result.message}")

    # Print statistics
    print("\n" + "=" * 60)
    print("STATISTICS")
    print(json.dumps(firewall.get_status(), indent=2))
