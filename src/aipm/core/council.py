"""
Council of Ouroboros - Multi-Agent Orchestration

Coordinates multiple workers exploring different branches of the 
Experiment Tree in parallel using Git worktrees.
"""

import os
import subprocess
import shutil
import time
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import multiprocessing

from .tree import ExperimentTree, ExperimentNode
from .goal import GoalState


@dataclass
class CouncilConfig:
    """Configuration for the Council."""
    workspace_path: Path
    worker_count: int = 4
    temp_dir: Path = Path("/tmp/ouroboros")
    iteration_delay: float = 2.0
    model: str = "claude-sonnet-4-6-20250514"


class WorktreeManager:
    """Manages isolated Git worktrees for workers."""

    def __init__(self, base_repo: Path, temp_root: Path):
        self.base_repo = base_repo.resolve()
        self.temp_root = temp_root.resolve()
        self.worktrees: Dict[str, Path] = {}

    def setup_worker(self, worker_id: str) -> Path:
        """Create a new Git worktree for a worker."""
        worktree_path = self.temp_root / worker_id
        if worktree_path.exists():
            self.cleanup_worker(worker_id)
        
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create worktree (using a detached HEAD at current master/main)
        try:
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path)],
                cwd=self.base_repo,
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create worktree: {e.stderr.decode()}")
            raise

        # Symlink .ouroboros directory so worker shares the same state
        master_ouroboros = self.base_repo / ".ouroboros"
        worker_ouroboros = worktree_path / ".ouroboros"
        
        if master_ouroboros.exists():
            os.symlink(master_ouroboros, worker_ouroboros)
        
        self.worktrees[worker_id] = worktree_path
        return worktree_path

    def cleanup_worker(self, worker_id: str):
        """Remove a worker's worktree."""
        if worker_id in self.worktrees:
            path = self.worktrees[worker_id]
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(path)],
                    cwd=self.base_repo,
                    check=True,
                    capture_output=True
                )
            except Exception as e:
                print(f"⚠️ Warning cleaning up worktree {worker_id}: {e}")
            
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            
            del self.worktrees[worker_id]

    def cleanup_all(self):
        """Remove all managed worktrees."""
        worker_ids = list(self.worktrees.keys())
        for wid in worker_ids:
            self.cleanup_worker(wid)


class CouncilOrchestrator:
    """The master process that coordinates workers."""

    def __init__(self, config: CouncilConfig):
        self.config = config
        self.wt_manager = WorktreeManager(config.workspace_path, config.temp_dir)
        self.ouroboros_dir = config.workspace_path / ".ouroboros"
        self.tree_file = self.ouroboros_dir / "tree.yaml"
        self.goal_file = self.ouroboros_dir / "goal.yaml"
        
        self.running = False
        self.processes: Dict[str, multiprocessing.Process] = {}

    def _worker_loop(self, worker_id: str, workspace: Path):
        """Subprocess entry point for a worker."""
        print(f"👷 Worker {worker_id} started in {workspace}")
        
        # Shared status file for this worker
        status_file = workspace / ".ouroboros" / f"status_{worker_id}.json"
        
        def report_status(state: str, details: str = ""):
            import json
            try:
                with open(status_file, "w") as f:
                    json.dump({"state": state, "details": details, "timestamp": time.time()}, f)
            except: pass

        try:
            report_status("initializing")
            # Invoke 'ouroboros run --max-iter 1' in the worker's workspace
            cmd = [
                "ouroboros", "run", 
                "--workspace", str(workspace),
                "--max-iter", "1",
                "--delay", "0"
            ]
            
            import sys
            import subprocess
            
            report_status("thinking", "Generating hypothesis...")
            
            result = subprocess.run(
                [sys.executable, "-m", "ouroboros.cli"] + cmd[1:], 
                capture_output=True, 
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                report_status("error", result.stderr[:100])
                print(f"❌ Worker {worker_id} failed with exit code {result.returncode}")
            else:
                report_status("finished", "Iteration complete")
                print(f"✅ Worker {worker_id} finished iteration.")
                
        except Exception as e:
            report_status("crashed", str(e))
            print(f"❌ Worker {worker_id} exception: {e}")

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

    def run(self):
        """Run the council until goal achieved or exhausted."""
        self.running = True
        print(f"👑 Council of Ouroboros started with {self.config.worker_count} workers.")
        
        # Initialize Tree if empty
        tree = ExperimentTree.load(self.tree_file)
        
        # NEW: Clear all locks on startup to prevent deadlocks from previous crashes
        locks_cleared = 0
        for node in tree.nodes.values():
            if node.locked_by:
                node.locked_by = None
                node.assigned_at = None
                locks_cleared += 1
        
        if locks_cleared > 0:
            print(f"🔓 Released {locks_cleared} stale locks from previous session.")

        if not tree.nodes:
            root_commit = self._get_current_commit()
            root_node = ExperimentNode(
                id="root",
                commit_hash=root_commit,
                metric=None,
                hypothesis="Initial state",
                status="baseline"
            )
            tree.add_node(root_node)
            print("🌳 Initialized tree with root node.")
        
        tree.save(self.tree_file)

        try:
            while self.running:
                # 1. Load latest state
                tree = ExperimentTree.load(self.tree_file)
                goal = GoalState.load(self.goal_file)
                
                if goal.is_exhausted() or goal.current_state == "achieved":
                    print("🏁 Goal achieved or limit reached. Shutting down council.")
                    break

                # 2. Check for available nodes and worker slots
                active_nodes = tree.get_active_frontier()
                available_slots = self.config.worker_count - len(self.processes)
                
                if not active_nodes and not self.processes:
                    print("💤 Waiting for active frontier nodes...")
                
                # 3. Clean up finished workers
                finished_workers = []
                for wid, proc in self.processes.items():
                    if not proc.is_alive():
                        finished_workers.append(wid)
                
                for wid in finished_workers:
                    # Release the node in the tree
                    node_id = self._get_node_for_worker(tree, wid)
                    if node_id:
                        tree.release_node(node_id)
                        tree.save(self.tree_file)
                    
                    self.processes[wid].join()
                    del self.processes[wid]
                    self.wt_manager.cleanup_worker(wid)
                    print(f"👷 Worker {wid} finished.")

                # 4. Assign work to available slots
                for i in range(available_slots):
                    if not active_nodes:
                        break
                    
                    # Claim the best available node
                    node = active_nodes.pop(0)
                    worker_id = f"worker-{int(time.time() * 1000) % 10000}-{i}"
                    
                    if tree.claim_node(node.id, worker_id):
                        print(f"🚀 Dispatching {worker_id} to explore path from {node.id}")
                        tree.save(self.tree_file)
                        
                        workspace = self.wt_manager.setup_worker(worker_id)
                        
                        proc = multiprocessing.Process(
                            target=self._worker_loop,
                            args=(worker_id, workspace)
                        )
                        proc.start()
                        self.processes[worker_id] = proc
                
                time.sleep(self.config.iteration_delay)

        except KeyboardInterrupt:
            print("\n🛑 Council received interrupt. Cleaning up...")
        finally:
            self.stop()

    def _get_node_for_worker(self, tree: ExperimentTree, worker_id: str) -> Optional[str]:
        for node in tree.nodes.values():
            if node.locked_by == worker_id:
                return node.id
        return None

    def stop(self):
        """Stop all workers and cleanup."""
        self.running = False
        print(f"🛑 Stopping {len(self.processes)} workers...")
        
        # Release all locked nodes in the tree
        try:
            tree = ExperimentTree.load(self.tree_file)
            for wid in self.processes.keys():
                node_id = self._get_node_for_worker(tree, wid)
                if node_id:
                    tree.release_node(node_id)
            tree.save(self.tree_file)
        except Exception as e:
            print(f"⚠️ Warning releasing nodes during stop: {e}")

        for wid, proc in self.processes.items():
            if proc.is_alive():
                os.kill(proc.pid, signal.SIGTERM)
                proc.join(timeout=2)
        
        self.wt_manager.cleanup_all()
        print("🧹 Council cleaned up.")
