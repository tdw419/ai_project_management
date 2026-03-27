"""
Ouroboros Loop - The Recursive Driver

Connects the brain (self-prompting) to the body (experiment execution).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING, List
import time
import subprocess
import os

from .goal import GoalState
from .prompt_generator import SelfPromptGenerator, ExperimentSpec
from .code_applier import CodeApplier
from .tree import ExperimentTree, ExperimentNode
from .ctrm_prompt_manager import CTRMPromptManager
from .unified_prompt_engine import create_default_engine, PromptCategory
from ..protocols.semantic_analyzer import SemanticAnalyzer

if TYPE_CHECKING:
    from .safety import SafetyManager

# Try to import the body (openspec+autoresearch)
# Falls back to simple shell execution if not available
try:
    from autospec.autoresearch.ascii_runtime import ASCIIExperimentRuntime
    HAS_AUTOSPEC = True
except ImportError:
    HAS_AUTOSPEC = False


@dataclass
class LoopConfig:
    """Configuration for the Ouroboros loop."""

    # Paths
    workspace_path: Path
    goal_file: Path
    results_file: Path
    tree_file: Path
    db_path: Optional[Path] = None  # Will use config.CTRM_DB if not provided

    # Timing
    iteration_delay_seconds: float = 5.0

    # LLM
    model: str = "claude-sonnet-4-6-20250514"

    # Execution
    dry_run: bool = False
    max_iterations: Optional[int] = None

    # Safety
    safety_manager: Optional["SafetyManager"] = None


class OuroborosLoop:
    """
    The recursive self-prompting loop with branching support.
    Integrated with CTRM and Unified Prompt Engine.
    """

    def __init__(self, config: LoopConfig):
        self.config = config
        self.project_root = config.workspace_path
        
        # 1. Initialize Components
        print("--- Initializing Ouroboros Core ---")
        from aipm.config import CTRM_DB
        db_path = config.db_path or CTRM_DB
        self.ctrm = CTRMPromptManager(db_path)
        self.engine = create_default_engine(self.project_root / ".ouroboros")
        self.semantic = SemanticAnalyzer(self.project_root / ".ouroboros/semantic")
        
        # Inject dependencies
        self.engine.semantic_analyzer = self.semantic
        self.engine.ascii_dashboard_path = self.project_root / ".ouroboros/dashboard.ascii"
        
        # Legacy components (refactored to use new ones internally)
        self.generator = SelfPromptGenerator(
            model=config.model, 
            project_root=self.project_root,
            use_unified_engine=True
        )
        self.applier = CodeApplier(workspace_path=config.workspace_path)
        
        self.goal: Optional[GoalState] = None
        self.tree = ExperimentTree.load(config.tree_file)
        self.current_node_id: Optional[str] = None

    def _get_current_commit(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], 
                cwd=self.config.workspace_path, 
                capture_output=True, 
                text=True, 
                check=True
            )
            return result.stdout.strip()
        except:
            return "0000000000000000000000000000000000000000"

    def _checkout_commit(self, commit_hash: str) -> bool:
        """Checkout a specific commit."""
        try:
            subprocess.run(
                ["git", "checkout", commit_hash], 
                cwd=self.config.workspace_path, 
                capture_output=True, 
                check=True
            )
            return True
        except Exception as e:
            print(f"❌ Error during checkout: {e}")
            return False

    def _is_exhausted(self, max_iterations: Optional[int] = None) -> bool:
        """Check if loop is exhausted (time or iterations)."""
        if self.goal is None:
            return True
        
        # Use goal's max_iterations if not overridden
        effective_max = max_iterations if max_iterations is not None else self.goal.max_iterations
        
        if self.goal.iterations >= effective_max:
            return True
            
        # Time check
        elapsed = datetime.now() - self.goal.created_at
        if elapsed.total_seconds() / 3600 >= self.goal.max_time_hours:
            return True
            
        return False

    def run(self) -> None:
        """Run the recursive loop until goal achieved or exhausted."""
        # Load or create goal
        if self.config.goal_file.exists():
            self.goal = GoalState.load(self.config.goal_file)
        else:
            raise ValueError(f"Goal file not found: {self.config.goal_file}")

        # In-memory override only
        current_max_iter = self.goal.max_iterations
        if self.config.max_iterations is not None:
            current_max_iter = self.config.max_iterations
        
        # Initialize ASCII Dashboard State
        self.engine.update_ascii_state(
            status="running",
            max_iterations=current_max_iter,
            experiment={"hypothesis": "Initializing...", "target": "N/A", "metric": "N/A", "budget": "N/A"}
        )

        # Initialize Tree if empty
        if not self.tree.nodes:
            root_commit = self._get_current_commit()
            root_node = ExperimentNode(
                id="root",
                commit_hash=root_commit,
                metric=None,
                hypothesis="Initial state",
                status="baseline"
            )
            self.tree.add_node(root_node)
            self.current_node_id = "root"
        else:
            # Resume from best node or last active node
            best = self.tree.get_best_node(lower_is_better=True)
            self.current_node_id = best.id if best else self.tree.root_id

        print(f"🎯 Goal: {self.goal.objective}")
        print(f"📊 Success criteria: {self.goal.success_criteria}")
        print(f"🔄 Starting loop (max {current_max_iter} iterations)")
        if self.config.dry_run:
            print("跑 DRY RUN MODE - no actual changes will be made")
        print()

        while not self._is_exhausted(current_max_iter):
            # Check if achieved
            if self.goal.best_metric is not None:
                if self.goal.is_achieved(self.goal.best_metric):
                    print(f"✅ Goal achieved! Metric: {self.goal.best_metric}")
                    self._update_goal_state("achieved")
                    self.engine.update_ascii_state(status="stopped")
                    break

            # 1. Context Collection
            tree_ascii = self.tree.generate_ascii_flowchart()
            codebase_context = self._read_codebase_context()

            # 2. Generate next experiment
            print(f"🔄 Iteration {self.goal.iterations + 1}/{current_max_iter}")
            print(f"📍 Current Path: {self.current_node_id}")
            
            # Update Dashboard for reasoning phase
            self.engine.update_ascii_state(status="running")
            
            spec = self.generator.generate_next(
                goal=self.goal.objective,
                success_criteria=self.goal.success_criteria,
                results_tsv=self.config.results_file,
                codebase_context=codebase_context,
                tree_ascii=tree_ascii
            )

            # Record reasoning action in CTRM
            self.ctrm.enqueue(
                f"Generated hypothesis: {spec.hypothesis} for target {spec.target}",
                priority=2,
                source="ouroboros_loop"
            )

            decision = spec.metadata.get("decision", "REFINE")
            if decision.startswith("PIVOT"):
                target_node_id = decision.split()[-1]
                target_node = self.tree.get_node(target_node_id)
                if target_node:
                    print(f"🔀 PIVOTING to node: {target_node_id}")
                    if not self.config.dry_run:
                        self._checkout_commit(target_node.commit_hash)
                    self.current_node_id = target_node_id
                else:
                    print(f"⚠️ Warning: Requested pivot to unknown node {target_node_id}. Refining current instead.")

            print(f"📋 Hypothesis: {spec.hypothesis}")
            print(f"📁 Target: {spec.target}")
            print(f"📏 Metric: {spec.metric}")
            print()

            self.goal = self.goal.increment()

            if self.config.dry_run:
                print("🏃 DRY RUN - skipping execution")
                print(spec.to_ascii())
                self._log_result(spec, {
                    "timestamp": datetime.now().isoformat(),
                    "status": "dry_run",
                    "metric": None,
                })
            else:
                # Execution
                start_time = time.time()
                
                # Update Dashboard for execution phase
                self.engine.write_ascii_dashboard(
                    status="running",
                    experiment={
                        "hypothesis": spec.hypothesis[:50],
                        "target": spec.target,
                        "metric": spec.metric,
                        "budget": spec.budget
                    },
                    tree={"nodes": [n.id for n in self.tree.nodes], "current": self.current_node_id}
                )
                
                result = self._execute_experiment(spec)
                elapsed = time.time() - start_time

                # Record outcome for semantic analysis
                self.semantic.record_action(
                    action_type="apply_code_change",
                    action_detail=f"H: {spec.hypothesis} T: {spec.target}",
                    metric_before=self.goal.best_metric or 0,
                    metric_after=result.get("metric") or (self.goal.best_metric or 0),
                    event_success=result.get("status") == "success"
                )

                # Update Tree
                timestamp_id = int(time.time() * 1000) % 100000
                new_node_id = f"node_{self.goal.iterations}_{timestamp_id}"

                parent_node = self.tree.get_node(self.current_node_id)
                convergence_rate = None
                if parent_node and parent_node.metric is not None and result.get("metric") is not None:
                    if parent_node.metric != 0:
                        convergence_rate = (result["metric"] - parent_node.metric) / abs(parent_node.metric)

                new_node = ExperimentNode(
                    id=new_node_id,
                    commit_hash=result.get("commit", self._get_current_commit()),
                    metric=result.get("metric"),
                    hypothesis=spec.hypothesis,
                    parent_id=self.current_node_id,
                    status="active" if result.get("status") == "keep" else "exhausted",
                    depth=parent_node.depth + 1 if parent_node else 0,
                    time_spent_seconds=elapsed,
                    iterations_at_node=1,
                    convergence_rate=convergence_rate
                )
                self.tree.add_node(new_node)
                
                # If we kept it, this becomes the new current node
                if result.get("status") == "keep":
                    self.current_node_id = new_node_id
                    if result.get("metric") is not None:
                        self.goal = self.goal.update_best(result["metric"])

                self._log_result(spec, result)
                self.tree.save(self.config.tree_file)

                print(f"📊 Result: {result.get('status', 'unknown')}")
                print(f"📈 Metric: {result.get('metric', 'N/A')}")
                print()

            self.goal.save(self.config.goal_file)

            if not self._is_exhausted(current_max_iter):
                self.engine.update_ascii_state(status="paused")
                time.sleep(self.config.iteration_delay_seconds)

        if self._is_exhausted(current_max_iter):
            print("⚠️ Loop exhausted")
            self._update_goal_state("exhausted")
            self.engine.update_ascii_state(status="stopped")

    def _read_codebase_context(self, max_files: int = 3, max_lines: int = 100) -> str:
        """Read relevant code files."""
        context_parts = []
        priority_files = ["pi_approximator.py", "train.py", "main.py", "app.py", "test.py"]
        found_files = []
        for filename in priority_files:
            filepath = self.config.workspace_path / filename
            if filepath.exists():
                found_files.append(filepath)

        if len(found_files) < max_files:
            for py_file in self.config.workspace_path.glob("*.py"):
                if py_file not in found_files and not py_file.name.startswith("."):
                    found_files.append(py_file)
                    if len(found_files) >= max_files: break

        for filepath in found_files[:max_files]:
            try:
                with open(filepath) as f:
                    lines = f.readlines()[:max_lines]
                content = "".join(lines)
                context_parts.append(f"### {filepath.name}\n```python\n{content}\n```")
            except Exception as e:
                context_parts.append(f"### {filepath.name}\nError: {e}")

        return "\n\n".join(context_parts) if context_parts else "No context"

    def _execute_experiment(self, spec: ExperimentSpec) -> dict:
        """Execute experiment."""
        result = {
            "hypothesis": spec.hypothesis,
            "target": spec.target,
            "status": "pending",
            "metric": None,
            "output": "",
            "timestamp": datetime.now().isoformat(),
        }
        try:
            if HAS_AUTOSPEC:
                result = self._execute_with_autospec(spec)
            else:
                if spec.code_changes: self.applier.apply(spec.code_changes)
                result = self._execute_with_shell(spec)
        except Exception as e:
            result["status"] = "error"
            result["output"] = str(e)
        return result

    def _execute_with_autospec(self, spec: ExperimentSpec) -> dict:
        """Execute using openspec+autoresearch runtime."""
        from autospec.autoresearch.loop import Hypothesis
        from autospec.autoresearch.ascii_spec import ASCIISpecParser

        try:
            runtime = ASCIIExperimentRuntime(self.config.workspace_path)
            parser = ASCIISpecParser()
            ascii_spec = parser.parse(spec.to_ascii())
            
            hypothesis = Hypothesis(
                task_id=ascii_spec.experiment_id or "AUTO",
                description=spec.hypothesis,
                expected_improvement=0.1,
                code_changes=spec.code_changes
            )
            
            loop = runtime._spec_to_loop(ascii_spec)
            exp_result = loop.run(hypothesis)

            return {
                "hypothesis": spec.hypothesis,
                "target": spec.target,
                "status": exp_result.status.value if hasattr(exp_result.status, 'value') else str(exp_result.status),
                "metric": exp_result.metric,
                "commit": exp_result.commit_hash,
                "output": getattr(exp_result, 'output', ''),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"DEBUG: _execute_with_autospec failed: {str(e)}")
            return {"status": "error", "output": str(e)}

    def _execute_with_shell(self, spec: ExperimentSpec) -> dict:
        """Fallback shell execution."""
        result = {"hypothesis": spec.hypothesis, "target": spec.target, "status": "pending", "metric": None, "output": "", "timestamp": datetime.now().isoformat()}
        try:
            eval_command = self._get_eval_command(spec)
            proc = subprocess.run(eval_command, shell=True, capture_output=True, text=True, cwd=self.config.workspace_path, timeout=300)
            result["output"] = proc.stdout + proc.stderr
            result["returncode"] = proc.returncode
            result["metric"] = self._extract_metric(result["output"], spec.metric)
            result["status"] = "success" if proc.returncode == 0 else "failed"
        except Exception as e:
            result["status"] = "error"
            result["output"] = str(e)
        return result

    def _get_eval_command(self, spec: ExperimentSpec) -> str:
        if self.config.workspace_path.joinpath("pytest.ini").exists(): return "pytest -v --tb=short"
        elif self.config.workspace_path.joinpath("test.py").exists(): return "python3 test.py"
        else: return f"python3 {spec.target}"

    def _extract_metric(self, output: str, metric_spec: str) -> Optional[float]:
        import re
        
        # 1. Look for explicit METRIC: prefix (preferred)
        metric_match = re.search(r"METRIC:\s*([-+]?\d*\.\d+|\d+)", output)
        if metric_match:
            return float(metric_match.group(1))
            
        # 2. Fallback to any float in the output
        matches = re.findall(r"[-+]?\d*\.\d+|\d+", output)
        if matches: return float(matches[0])
        return None

    def _log_result(self, spec: ExperimentSpec, result: dict) -> None:
        """Append result to the results log (TSV format) with locking."""
        import fcntl
        header = "timestamp\thypothesis\ttarget\tstatus\tmetric\n"
        row = f"{result['timestamp']}\t{spec.hypothesis[:50]}\t{spec.target}\t{result['status']}\t{result['metric']}\n"
        
        # Create file with header if it doesn't exist
        if not self.config.results_file.exists():
            with open(self.config.results_file, "w") as f:
                f.write(header)

        with open(self.config.results_file, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write(row)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _update_goal_state(self, state: str) -> None:
        if self.goal:
            self.goal.current_state = state
            self.goal.save(self.config.goal_file)
