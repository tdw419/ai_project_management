"""
Monte Carlo Branching -- run multiple strategies in parallel via git worktrees.

Instead of serial retries, when an issue hits attempt 2+:
  1. Create N git worktrees (one per strategy)
  2. Run pi agent in each worktree simultaneously
  3. Parse outcomes from all workers
  4. Pick the best result (highest test delta / success)
  5. Merge the winner back to the main branch
  6. Clean up worktrees

This dramatically improves success rates because the system tries
completely different approaches simultaneously instead of guessing.
"""

import asyncio
import subprocess
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from .outcome import PiOutcome, OutcomeStatus, parse_outcome
from .prompt_strategies import Strategy


@dataclass
class WorkerResult:
    """Result from one parallel worker."""
    strategy: Strategy
    worktree_path: str
    outcome: Optional[PiOutcome] = None
    prompt_text: str = ""
    duration: float = 0.0

    @property
    def score(self) -> float:
        """Score for ranking results. Higher is better."""
        if not self.outcome:
            return -100.0
        o = self.outcome
        if o.status == OutcomeStatus.SUCCESS:
            return 100.0 + o.test_delta
        elif o.status == OutcomeStatus.PARTIAL:
            # Partial is worth something if code changed
            return 50.0 + o.test_delta
        elif o.status == OutcomeStatus.NO_CHANGE:
            return 10.0
        else:
            return o.test_delta  # negative = bad


class MonteCarloRunner:
    """Run multiple strategies in parallel using git worktrees."""

    def __init__(self, repo_path: str, max_workers: int = 3):
        self.repo_path = Path(repo_path).resolve()
        self.max_workers = max_workers
        self.worktrees: List[str] = []

    def create_worktree(self, branch_suffix: str) -> Optional[str]:
        """Create a git worktree for a parallel worker.

        Returns the worktree path on success, None on failure.
        """
        worktree_path = str(self.repo_path.parent / f".aipm-worktree-{branch_suffix}")

        try:
            # Create a new branch and worktree
            result = subprocess.run(
                ["git", "worktree", "add", worktree_path, "-b", f"aipm/mc-{branch_suffix}", "HEAD"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                # Branch might already exist, try without creating
                result = subprocess.run(
                    ["git", "worktree", "add", worktree_path, f"aipm/mc-{branch_suffix}"],
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    return None

            self.worktrees.append(worktree_path)
            return worktree_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def cleanup_worktrees(self):
        """Remove all worktrees created by this runner."""
        for wt in self.worktrees:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", wt, "--force"],
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=15,
                )
                # Also try removing the branch
                branch = Path(wt).name.replace(".aipm-worktree-", "aipm/mc-")
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=10,
                )
            except Exception:
                pass
            # Remove directory if it still exists
            if Path(wt).exists():
                shutil.rmtree(wt, ignore_errors=True)
        self.worktrees.clear()

    async def run_parallel(
        self,
        prompts: Dict[Strategy, str],
        pi_model: str = "",
        timeout: int = 300,
    ) -> List[WorkerResult]:
        """Run multiple strategies in parallel.

        Args:
            prompts: Map of strategy -> prompt text
            pi_model: Model to use for pi agent
            timeout: Max seconds per worker

        Returns:
            List of WorkerResult, sorted by score (best first)
        """
        workers = list(prompts.items())[:self.max_workers]
        if not workers:
            return []

        # Create worktrees
        worktree_map: Dict[Strategy, str] = {}
        for strategy, _ in workers:
            suffix = strategy.value
            wt_path = self.create_worktree(suffix)
            if wt_path:
                worktree_map[strategy] = wt_path

        if not worktree_map:
            return []

        # Run all workers in parallel
        tasks = []
        for strategy, prompt in workers:
            wt_path = worktree_map.get(strategy)
            if not wt_path:
                continue
            task = asyncio.create_task(
                self._run_worker(strategy, wt_path, prompt, pi_model, timeout)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        worker_results: List[WorkerResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                strategy = workers[i][0]
                worker_results.append(WorkerResult(
                    strategy=strategy,
                    worktree_path=worktree_map.get(strategy, ""),
                ))
            else:
                worker_results.append(result)

        # Sort by score (best first)
        worker_results.sort(key=lambda r: r.score, reverse=True)
        return worker_results

    async def _run_worker(
        self,
        strategy: Strategy,
        worktree_path: str,
        prompt_text: str,
        pi_model: str,
        timeout: int,
    ) -> WorkerResult:
        """Run a single pi agent in a worktree."""
        start = time.time()
        result = WorkerResult(
            strategy=strategy,
            worktree_path=worktree_path,
            prompt_text=prompt_text,
        )

        try:
            cmd = ["hermes", "chat", "-q", prompt_text, "-Q", "--yolo"]
            if pi_model:
                cmd.extend(["-m", pi_model])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            raw_output = (stdout.decode() + "\n" + stderr.decode())
            exit_code = proc.returncode

            # Capture state from worktree
            tests_before = (0, 0)
            tests_after = (0, 0)
            file_changes = {}

            # Get git diff from worktree
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "--name-status", "HEAD"],
                    cwd=worktree_path,
                    capture_output=True, text=True, timeout=10,
                )
                for line in diff_result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            action_map = {"A": "added", "M": "modified", "D": "deleted"}
                            file_changes[parts[1]] = action_map.get(parts[0], "modified")
            except Exception:
                pass

            result.outcome = parse_outcome(
                raw_output=raw_output,
                exit_code=exit_code,
                file_changes=file_changes,
                tests_before=tests_before,
                tests_after=tests_after,
                attempt_number=1,  # each worker is independent
            )

        except asyncio.TimeoutError:
            result.outcome = PiOutcome(
                status=OutcomeStatus.TIMEOUT,
                exit_code=-1,
                attempt_number=1,
            )
        except Exception as e:
            result.outcome = PiOutcome(
                status=OutcomeStatus.ERROR,
                exit_code=-1,
                raw_output=str(e),
                attempt_number=1,
            )

        result.duration = time.time() - start
        return result

    def merge_winner(self, winner: WorkerResult, target_branch: str = "main") -> bool:
        """Merge the winning worktree's changes back to the target branch.

        Returns True if merge succeeded.
        """
        if not winner.outcome or winner.outcome.status != OutcomeStatus.SUCCESS:
            return False

        try:
            # Get the branch name from the worktree
            branch = f"aipm/mc-{winner.strategy.value}"

            # Switch to target branch and merge
            subprocess.run(
                ["git", "checkout", target_branch],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=10,
            )
            result = subprocess.run(
                ["git", "merge", branch, "--no-edit"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False


def get_diff_summary(repo_path: str) -> str:
    """Get a git diff --stat summary for the current changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_path,
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip()[:2000]
    except Exception:
        return ""
