"""
Safety Verification & Sandboxing Protocol

A containment-first execution environment that simulates modifications
before applying them, ensuring integrity over performance.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any
from enum import Enum
import ast
import re
import json
import subprocess
import tempfile
import shutil


class ViolationType(Enum):
    PROTECTED_FILE_ACCESS = "protected_file_access"
    FORBIDDEN_OPERATION = "forbidden_operation"
    MEMORY_BOUND_EXCEEDED = "memory_bound_exceeded"
    INFINITE_LOOP_RISK = "infinite_loop_risk"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    SYNTAX_ERROR = "syntax_error"


class Severity(Enum):
    WARNING = "warning"      # Log but allow
    ERROR = "error"          # Block modification
    CRITICAL = "critical"    # Block and alert


@dataclass
class SafetyViolation:
    """A detected safety violation."""
    violation_type: ViolationType
    severity: Severity
    message: str
    location: Optional[str] = None
    remediation: Optional[str] = None


@dataclass
class SandboxResult:
    """Result of sandbox simulation."""
    safe: bool
    violations: list[SafetyViolation]
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0
    output: str = ""
    rollback_triggered: bool = False


@dataclass
class SafetyConfig:
    """Configuration for safety constraints."""
    # Protected patterns - cannot be modified
    protected_files: list[str] = field(default_factory=lambda: [
        "safety.py",
        "sandbox.py",
        "evaluation.py",
        "goal.py",
        "self_modification.py",
    ])

    # Forbidden operations in code
    forbidden_patterns: list[str] = field(default_factory=lambda: [
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__\s*\(",
        r"compile\s*\(",
        r"open\s*\([^)]*,\s*['\"]w['\"]",  # File writes (with write mode)
        r"os\.system\s*\(",
        r"subprocess\.(call|run|Popen)",
        r"shutil\.rmtree",
    ])

    # Resource limits
    max_memory_mb: float = 512.0
    max_execution_time_ms: float = 5000.0
    max_file_size_kb: float = 100.0
    max_recursion_depth: int = 100

    # Behavior limits
    max_loop_iterations: int = 10000
    allow_network: bool = False
    allow_file_write: bool = False


class SafetyValidator:
    """
    Validates code modifications against safety constraints.

    Three-phase validation:
    1. STATIC - Parse and analyze code structure
    2. SIMULATE - Run in sandboxed environment
    3. VERIFY - Check runtime behavior
    """

    def __init__(self, config: SafetyConfig, workspace: Path):
        self.config = config
        self.workspace = workspace
        self.violations: list[SafetyViolation] = []

    # === PHASE 1: STATIC ANALYSIS ===

    def validate_static(self, code: str, target_file: Path) -> list[SafetyViolation]:
        """
        Static analysis - no execution required.

        Checks:
        - Syntax validity
        - Protected file access
        - Forbidden patterns
        - AST analysis for dangerous constructs
        """
        violations = []

        # 1. Syntax check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            violations.append(SafetyViolation(
                violation_type=ViolationType.SYNTAX_ERROR,
                severity=Severity.ERROR,
                message=f"Syntax error: {e.msg}",
                location=f"line {e.lineno}",
                remediation="Fix syntax before submission"
            ))
            return violations  # Can't continue if syntax is broken

        # 2. Protected file check
        for protected in self.config.protected_files:
            if protected in str(target_file):
                violations.append(SafetyViolation(
                    violation_type=ViolationType.PROTECTED_FILE_ACCESS,
                    severity=Severity.CRITICAL,
                    message=f"Attempt to modify protected file: {protected}",
                    location=str(target_file),
                    remediation="This file cannot be modified by the AI"
                ))

        # 3. Forbidden patterns check
        for pattern in self.config.forbidden_patterns:
            matches = re.findall(pattern, code)
            if matches:
                violations.append(SafetyViolation(
                    violation_type=ViolationType.FORBIDDEN_OPERATION,
                    severity=Severity.ERROR,
                    message=f"Forbidden operation detected: {pattern}",
                    remediation="Remove or replace this operation"
                ))

        # 4. AST analysis for dangerous constructs
        violations.extend(self._analyze_ast(tree))

        return violations

    def _analyze_ast(self, tree: ast.AST) -> list[SafetyViolation]:
        """Analyze AST for dangerous patterns."""
        violations = []

        for node in ast.walk(tree):
            # Check for infinite loop risks
            if isinstance(node, ast.While):
                # Check if there's a break condition
                has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                if not has_break:
                    violations.append(SafetyViolation(
                        violation_type=ViolationType.INFINITE_LOOP_RISK,
                        severity=Severity.WARNING,
                        message="While loop without explicit break",
                        remediation="Add break condition or iteration limit"
                    ))

            # Check for deep recursion
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                # Check if function calls itself
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name) and child.func.id == func_name:
                            violations.append(SafetyViolation(
                                violation_type=ViolationType.INFINITE_LOOP_RISK,
                                severity=Severity.WARNING,
                                message=f"Recursive function: {func_name}",
                                remediation="Ensure base case exists and recursion depth is limited"
                            ))

        return violations

    # === PHASE 2: SANDBOX SIMULATION ===

    def simulate(self, code: str, test_input: Any = None) -> SandboxResult:
        """
        Execute code in sandboxed environment.

        Uses subprocess isolation for containment.
        """
        start_time = datetime.now()
        violations = []

        # Create temporary sandbox directory
        sandbox_dir = tempfile.mkdtemp(prefix="ouroboros_sandbox_")

        try:
            # Write code to sandbox
            sandbox_file = Path(sandbox_dir) / "sandboxed_code.py"
            sandbox_file.write_text(code)

            # Run in subprocess with resource limits
            try:
                result = subprocess.run(
                    ["python3", "-c", f"""
import resource
import sys

# Set memory limit
resource.setrlimit(resource.RLIMIT_AS, (
    {int(self.config.max_memory_mb * 1024 * 1024)},
    {int(self.config.max_memory_mb * 1024 * 1024)}
))

# Set CPU time limit
resource.setrlimit(resource.RLIMIT_CPU, (
    {int(self.config.max_execution_time_ms / 1000) + 1},
    {int(self.config.max_execution_time_ms / 1000) + 1}
))

# Execute the code
exec(open('{sandbox_file}').read())
"""],
                    capture_output=True,
                    text=True,
                    timeout=self.config.max_execution_time_ms / 1000,
                    cwd=sandbox_dir,
                )

                output = result.stdout + result.stderr
                execution_time = (datetime.now() - start_time).total_seconds() * 1000

                if result.returncode != 0:
                    violations.append(SafetyViolation(
                        violation_type=ViolationType.FORBIDDEN_OPERATION,
                        severity=Severity.ERROR,
                        message=f"Execution failed: {result.stderr}",
                    ))

            except subprocess.TimeoutExpired:
                violations.append(SafetyViolation(
                    violation_type=ViolationType.INFINITE_LOOP_RISK,
                    severity=Severity.ERROR,
                    message="Execution timed out",
                    remediation="Reduce complexity or add early termination"
                ))
                execution_time = self.config.max_execution_time_ms
                output = "TIMEOUT"

            except MemoryError:
                violations.append(SafetyViolation(
                    violation_type=ViolationType.MEMORY_BOUND_EXCEEDED,
                    severity=Severity.ERROR,
                    message="Memory limit exceeded",
                    remediation="Reduce memory usage"
                ))
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                output = "OUT_OF_MEMORY"

        finally:
            # Cleanup sandbox
            shutil.rmtree(sandbox_dir, ignore_errors=True)

        # Determine if safe
        safe = all(v.severity != Severity.ERROR and v.severity != Severity.CRITICAL
                   for v in violations)

        return SandboxResult(
            safe=safe,
            violations=violations,
            execution_time_ms=execution_time,
            output=output,
            rollback_triggered=not safe
        )

    # === PHASE 3: RUNTIME VERIFICATION ===

    def verify_runtime(self, result: SandboxResult) -> bool:
        """
        Post-execution verification.

        Checks:
        - No errors occurred
        - Resource limits respected
        - Output is valid
        """
        if not result.safe:
            return False

        if result.rollback_triggered:
            return False

        # Check execution time
        if result.execution_time_ms > self.config.max_execution_time_ms:
            return False

        return True

    # === FULL VALIDATION PIPELINE ===

    def validate(self, code: str, target_file: Path) -> SandboxResult:
        """
        Run full validation pipeline.

        STATIC → SIMULATE → VERIFY

        If any phase fails, triggers automatic rollback.
        """
        self.violations = []

        # Phase 1: Static analysis
        static_violations = self.validate_static(code, target_file)
        self.violations.extend(static_violations)

        # Check for critical violations - abort immediately
        critical = [v for v in static_violations if v.severity == Severity.CRITICAL]
        if critical:
            return SandboxResult(
                safe=False,
                violations=self.violations,
                rollback_triggered=True,
            )

        # Check for errors - skip simulation
        errors = [v for v in static_violations if v.severity == Severity.ERROR]
        if errors:
            return SandboxResult(
                safe=False,
                violations=self.violations,
                rollback_triggered=True,
            )

        # Phase 2: Sandbox simulation
        sandbox_result = self.simulate(code)
        self.violations.extend(sandbox_result.violations)

        # Phase 3: Runtime verification
        if not self.verify_runtime(sandbox_result):
            sandbox_result.safe = False
            sandbox_result.rollback_triggered = True

        return sandbox_result

    def get_report(self) -> str:
        """Generate human-readable safety report."""
        lines = ["=" * 50, "SAFETY VALIDATION REPORT", "=" * 50, ""]

        if not self.violations:
            lines.append("✅ No violations detected")
        else:
            for v in self.violations:
                icon = {"warning": "⚠️", "error": "❌", "critical": "🚨"}.get(v.severity.value, "❓")
                lines.append(f"{icon} [{v.severity.value.upper()}] {v.violation_type.value}")
                lines.append(f"   {v.message}")
                if v.location:
                    lines.append(f"   Location: {v.location}")
                if v.remediation:
                    lines.append(f"   Fix: {v.remediation}")
                lines.append("")

        return "\n".join(lines)


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    config = SafetyConfig()
    validator = SafetyValidator(config, Path("."))

    # Test safe code
    safe_code = """
def add(a, b):
    return a + b

result = add(1, 2)
print(result)
"""

    result = validator.validate(safe_code, Path("test.py"))
    print(validator.get_report())
    print(f"Safe: {result.safe}")

    # Test unsafe code
    print("\n" + "=" * 50 + "\n")

    unsafe_code = """
# Attempting forbidden operation
eval("print('hello')")
"""

    result = validator.validate(unsafe_code, Path("test.py"))
    print(validator.get_report())
    print(f"Safe: {result.safe}")
    print(f"Rollback triggered: {result.rollback_triggered}")
