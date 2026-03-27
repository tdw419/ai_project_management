"""
ASCII Experiment Runtime

Integrates ASCII spec format with AutoResearch experiment loop.

Usage:
    from autospec.autoresearch.ascii_runtime import run_ascii_spec
    
    result = run_ascii_spec(
        spec_text="H: Use AdamW\\nT: train.py\\nM: val_bpb < 0.7\\nB: 5",
        project_path=Path("/path/to/project")
    )
"""

from pathlib import Path

from .ascii_spec import (
    ASCIISpec, 
    ASCIISpecParser, 
    ASCIISpecRenderer,
    render_result
)
from .loop import Hypothesis, ExperimentLoop
from .result import ExperimentResult


class ASCIIExperimentRuntime:
    """Runtime for executing ASCII experiment specs."""
    
    def __init__(self, project_path: Path):
        """Initialize runtime.
        
        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path)
        self.parser = ASCIISpecParser()
        self.renderer = ASCIISpecRenderer()
    
    def run(self, spec_text: str) -> ExperimentResult:
        """Run an experiment from ASCII spec text.
        
        Args:
            spec_text: ASCII spec in any layer format
            
        Returns:
            ExperimentResult from running the experiment
        """
        # Parse the spec
        spec = self.parser.parse(spec_text)
        
        # Convert to Hypothesis and ExperimentLoop
        hypothesis = self._spec_to_hypothesis(spec)
        loop = self._spec_to_loop(spec)
        
        # Run the experiment
        result = loop.run(hypothesis)
        
        return result
    
    def run_with_visualization(self, spec_text: str) -> tuple[ExperimentResult, str]:
        """Run experiment and return result as ASCII visualization.
        
        Args:
            spec_text: ASCII spec in any layer format
            
        Returns:
            Tuple of (ExperimentResult, ASCII result visualization)
        """
        spec = self.parser.parse(spec_text)
        hypothesis = self._spec_to_hypothesis(spec)
        loop = self._spec_to_loop(spec)
        
        # Run the experiment
        result = loop.run(hypothesis)
        
        # Render result as ASCII
        result_ascii = render_result(result, spec)
        
        return result, result_ascii
    
    def _spec_to_hypothesis(self, spec: ASCIISpec) -> Hypothesis:
        """Convert ASCIISpec to Hypothesis object.
        
        Note: Code changes need to be generated separately.
        This creates a hypothesis with empty code_changes.
        """
        task_id = spec.experiment_id or self._generate_task_id(spec)
        
        return Hypothesis(
            task_id=task_id,
            description=spec.hypothesis,
            expected_improvement=self._estimate_improvement(spec),
            code_changes={}  # To be filled by code generator
        )
    
    def _spec_to_loop(self, spec: ASCIISpec) -> ExperimentLoop:
        """Convert ASCIISpec to ExperimentLoop object."""
        # Build eval command based on target file
        # This is a simple heuristic - could be customized
        eval_command = self._build_eval_command(spec)
        
        return ExperimentLoop(
            project_path=self.project_path,
            target_file=spec.target,
            eval_command=eval_command,
            time_budget_minutes=spec.budget_minutes,
            lower_is_better=spec.lower_is_better
        )
    
    def _generate_task_id(self, spec: ASCIISpec) -> str:
        """Generate a task ID from spec."""
        # Use experiment ID if available, otherwise generate from hash
        if spec.experiment_id:
            return spec.experiment_id
        
        # Hash the hypothesis
        import hashlib
        hash_obj = hashlib.md5(spec.hypothesis.encode())
        return f"EXP-{hash_obj.hexdigest()[:8].upper()}"
    
    def _estimate_improvement(self, spec: ASCIISpec) -> float:
        """Estimate expected improvement from metric.
        
        This is a heuristic based on the metric target.
        """
        # If we have a metric value, estimate improvement
        if spec.metric_value > 0:
            # Assume we want to reach the target
            # Improvement = target - current (simplified)
            return spec.metric_value * 0.1  # 10% improvement as default
        return 0.1  # Default 10% improvement
    
    def _build_eval_command(self, spec: ASCIISpec) -> str:
        """Build evaluation command from spec.
        
        This is a simple heuristic. Real implementation would:
        1. Check if there's a standard test script
        2. Look for package.json scripts
        3. Use configured eval command
        """
        target = spec.target
        
        # Python files
        if target.endswith('.py'):
            return f"python3 {target}"
        
        # Shell scripts
        if target.endswith('.sh'):
            return f"bash {target}"
        
        # Makefiles
        if target == 'Makefile' or target.startswith('make '):
            return "make test"
        
        # Default: try to run as executable
        return f"./{target}"


def run_ascii_spec(
    spec_text: str, 
    project_path: Path,
    visualize: bool = False
) -> ExperimentResult | tuple[ExperimentResult, str]:
    """Run an ASCII experiment spec.
    
    Args:
        spec_text: ASCII spec text (any layer)
        project_path: Path to project directory
        visualize: If True, return (result, ascii_visualization)
        
    Returns:
        ExperimentResult, or tuple with visualization if visualize=True
    """
    runtime = ASCIIExperimentRuntime(project_path)
    
    if visualize:
        return runtime.run_with_visualization(spec_text)
    else:
        return runtime.run(spec_text)


def demo():
    """Demo of ASCII spec runtime."""
    import tempfile
    from pathlib import Path
    
    # Create temp project
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        
        # Create a simple target file that outputs a metric
        target_file = project_path / "train.py"
        target_file.write_text("""
# Simulated training script
print("Training...")
print("val_bpb: 0.71")
print("Done.")
""")
        
        # Initialize git repo (required by ExperimentLoop)
        import subprocess
        subprocess.run(["git", "init"], cwd=project_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project_path, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=project_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=project_path, capture_output=True)
        
        # Create ASCII spec
        spec_text = """H: Use AdamW optimizer instead of SGD
T: train.py
M: val_bpb < 0.7
B: 5"""
        
        print("=== ASCII Spec ===")
        print(spec_text)
        print()
        
        # Run with visualization
        runtime = ASCIIExperimentRuntime(project_path)
        result, result_ascii = runtime.run_with_visualization(spec_text)
        
        print("=== Result ===")
        print(result_ascii)
        print()
        
        print(f"Status: {result.status}")
        print(f"Metric: {result.metric}")
        print(f"Commit: {result.commit_hash}")


if __name__ == '__main__':
    demo()
