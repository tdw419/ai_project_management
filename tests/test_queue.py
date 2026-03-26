"""Tests for AIPM queue and project management"""

import pytest
import tempfile
from pathlib import Path

from aipm.core.queue import PromptQueue
from aipm.core.engine import Prompt, PromptCategory, PromptStatus
from aipm.project.manager import ProjectManager, TaskPriority, TaskStatus


class TestPromptQueue:
    """Tests for PromptQueue class"""
    
    @pytest.fixture
    def queue(self):
        """Create a temporary queue for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield PromptQueue(Path(tmpdir) / "test.db")
    
    def test_add_prompt(self, queue):
        """Test adding a prompt"""
        prompt = Prompt(
            id="test_1",
            text="Test prompt",
            category=PromptCategory.CODE_GEN,
        )
        
        queue.add(prompt)
        
        retrieved = queue.get("test_1")
        assert retrieved is not None
        assert retrieved.text == "Test prompt"
    
    def test_get_pending(self, queue):
        """Test getting pending prompts"""
        for i in range(5):
            prompt = Prompt(
                id=f"test_{i}",
                text=f"Prompt {i}",
                category=PromptCategory.CODE_GEN,
                priority=i + 1,
            )
            queue.add(prompt)
        
        pending = queue.get_pending()
        assert len(pending) == 5
        
        # Should be sorted by priority
        assert pending[0].priority == 1
    
    def test_update_status(self, queue):
        """Test updating prompt status"""
        prompt = Prompt(
            id="test_1",
            text="Test",
            category=PromptCategory.CODE_GEN,
        )
        queue.add(prompt)
        
        prompt.status = PromptStatus.COMPLETED
        queue.update(prompt)
        
        retrieved = queue.get("test_1")
        assert retrieved.status == PromptStatus.COMPLETED
    
    def test_stats(self, queue):
        """Test queue statistics"""
        for i in range(3):
            prompt = Prompt(
                id=f"test_{i}",
                text=f"Prompt {i}",
                category=PromptCategory.CODE_GEN,
                status=PromptStatus.COMPLETED if i == 0 else PromptStatus.PENDING,
            )
            queue.add(prompt)
        
        stats = queue.get_stats()
        assert stats["total"] == 3
        assert stats["pending"] == 2
        assert stats["by_status"]["completed"] == 1


class TestProjectManager:
    """Tests for ProjectManager class"""
    
    @pytest.fixture
    def pm(self):
        """Create a temporary project manager for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ProjectManager(Path(tmpdir) / "test.db")
    
    def test_create_project(self, pm):
        """Test creating a project"""
        project = pm.create_project(
            name="Test Project",
            goal="Build something cool",
        )
        
        assert project.id.startswith("proj_")
        assert project.name == "Test Project"
        
        # Should be retrievable
        retrieved = pm.get_project(project.id)
        assert retrieved is not None
    
    def test_add_task(self, pm):
        """Test adding a task"""
        project = pm.create_project(
            name="Test",
            goal="Test goal",
        )
        
        task = pm.add_task(
            project_id=project.id,
            name="Implement feature",
            description="Add the new feature",
            priority=TaskPriority.HIGH,
        )
        
        assert task.id.startswith("task_")
        assert task.project_id == project.id
        
        # Should be in project tasks
        tasks = pm.get_project_tasks(project.id)
        assert len(tasks) == 1
    
    def test_task_dependencies(self, pm):
        """Test task dependencies"""
        project = pm.create_project(name="Test", goal="Test")
        
        task1 = pm.add_task(
            project_id=project.id,
            name="First task",
        )
        
        task2 = pm.add_task(
            project_id=project.id,
            name="Second task",
            dependencies=[task1.id],
        )
        
        # Mark first task as complete
        pm.update_task_status(task1.id, TaskStatus.COMPLETED)
        
        # Second task should now be ready
        ready = pm.get_ready_tasks(project.id)
        assert len(ready) == 1
        assert ready[0].id == task2.id
    
    def test_project_stats(self, pm):
        """Test project statistics"""
        project = pm.create_project(name="Test", goal="Test")
        
        for i in range(4):
            task = pm.add_task(
                project_id=project.id,
                name=f"Task {i}",
            )
            if i < 2:
                pm.update_task_status(task.id, TaskStatus.COMPLETED)
        
        stats = pm.get_project_stats(project.id)
        
        assert stats["total_tasks"] == 4
        assert stats["completed"] == 2
        assert stats["completion_percentage"] == 50.0
    
    def test_milestones(self, pm):
        """Test milestones"""
        project = pm.create_project(name="Test", goal="Test")
        
        milestone = pm.add_milestone(
            project_id=project.id,
            name="v1.0",
            description="First release",
        )
        
        milestones = pm.get_project_milestones(project.id)
        assert len(milestones) == 1
        assert milestones[0].name == "v1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
