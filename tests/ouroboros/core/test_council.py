import pytest
import os
import shutil
import subprocess
import signal
import multiprocessing
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from ouroboros.core.council import CouncilConfig, WorktreeManager, CouncilOrchestrator
from ouroboros.core.tree import ExperimentTree, ExperimentNode
from ouroboros.core.goal import GoalState

@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    
    # Init git repo
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True)
    
    # Create initial commit
    (workspace / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=workspace, check=True)
    
    # Create .ouroboros dir
    (workspace / ".ouroboros").mkdir()
    
    return workspace

class TestWorktreeManager:
    def test_setup_and_cleanup_worker(self, temp_workspace, tmp_path):
        temp_root = tmp_path / "worktrees"
        manager = WorktreeManager(temp_workspace, temp_root)
        
        worker_id = "worker-1"
        worktree_path = manager.setup_worker(worker_id)
        
        assert worktree_path.exists()
        assert (worktree_path / ".git").exists()
        assert (worktree_path / ".ouroboros").is_symlink()
        assert worker_id in manager.worktrees
        
        manager.cleanup_worker(worker_id)
        assert not worktree_path.exists()
        assert worker_id not in manager.worktrees

    def test_cleanup_all(self, temp_workspace, tmp_path):
        temp_root = tmp_path / "worktrees"
        manager = WorktreeManager(temp_workspace, temp_root)
        
        manager.setup_worker("w1")
        manager.setup_worker("w2")
        
        assert len(manager.worktrees) == 2
        manager.cleanup_all()
        assert len(manager.worktrees) == 0
        assert not (temp_root / "w1").exists()
        assert not (temp_root / "w2").exists()

class TestCouncilOrchestrator:
    @patch("multiprocessing.Process")
    @patch("subprocess.run")
    def test_orchestrator_lifecycle(self, mock_run, mock_process, temp_workspace, tmp_path):
        # Setup goal and tree
        goal_file = temp_workspace / ".ouroboros" / "goal.yaml"
        tree_file = temp_workspace / ".ouroboros" / "tree.yaml"
        
        goal = GoalState(objective="test", success_criteria="METRIC > 10")
        goal.save(goal_file)
        
        tree = ExperimentTree()
        root = ExperimentNode(id="root", commit_hash="abc", metric=None, hypothesis="root")
        tree.add_node(root)
        tree.save(tree_file)
        
        config = CouncilConfig(
            workspace_path=temp_workspace,
            worker_count=2,
            temp_dir=tmp_path / "council_work",
            iteration_delay=0.1
        )
        
        orchestrator = CouncilOrchestrator(config)
        
        # Mock WorktreeManager to avoid real git calls
        orchestrator.wt_manager = MagicMock()
        orchestrator.wt_manager.setup_worker.return_value = tmp_path / "mock-worker-ws"
        (tmp_path / "mock-worker-ws" / ".ouroboros").mkdir(parents=True, exist_ok=True)

        # Mock process to finish immediately
        mock_proc_instance = MagicMock()
        mock_proc_instance.is_alive.return_value = False
        mock_process.return_value = mock_proc_instance
        
        # Run for a short time
        def stop_after_a_bit():
            time.sleep(0.5)
            orchestrator.running = False
            
        import threading
        threading.Thread(target=stop_after_a_bit).start()
        
        orchestrator.run()
        
        # Verify workers were spawned
        assert mock_process.call_count >= 1
        
        # Check if locks were cleared/released
        final_tree = ExperimentTree.load(tree_file)
        for node in final_tree.nodes.values():
            assert node.locked_by is None

    def test_worker_loop_execution(self, temp_workspace, tmp_path):
        # This test verifies the _worker_loop method's logic
        config = CouncilConfig(workspace_path=temp_workspace)
        orchestrator = CouncilOrchestrator(config)
        
        worker_workspace = tmp_path / "worker-ws"
        worker_workspace.mkdir()
        (worker_workspace / ".ouroboros").mkdir()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator._worker_loop("test-worker", worker_workspace)
            
            # Verify status file was created and updated
            status_file = worker_workspace / ".ouroboros" / "status_test-worker.json"
            assert status_file.exists()
            
            import json
            status_data = json.loads(status_file.read_text())
            assert status_data["state"] == "finished"

    def test_get_node_for_worker(self):
        tree = ExperimentTree()
        n1 = ExperimentNode(id="n1", commit_hash="a", metric=1, hypothesis="h", locked_by="w1")
        tree.add_node(n1)
        
        orchestrator = CouncilOrchestrator(MagicMock(workspace_path=Path(".")))
        assert orchestrator._get_node_for_worker(tree, "w1") == "n1"
        assert orchestrator._get_node_for_worker(tree, "w2") is None

    def test_stop_cleanup(self, temp_workspace, tmp_path):
        config = CouncilConfig(workspace_path=temp_workspace, temp_dir=tmp_path / "temp")
        orchestrator = CouncilOrchestrator(config)
        
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = True
        orchestrator.processes["w1"] = mock_proc
        
        # Mock worktree manager to avoid real git calls
        orchestrator.wt_manager = MagicMock()
        
        with patch("os.kill") as mock_kill:
            orchestrator.stop()
            assert mock_kill.called
            assert orchestrator.wt_manager.cleanup_all.called
