import pytest
import sqlite3
import json
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from src.ouroboros.core.ctrm_prompt_manager import CTRMPromptManager

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database with prompt_queue table."""
    db_path = tmp_path / "test_ctrm.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE prompt_queue (
                id TEXT PRIMARY KEY,
                prompt TEXT,
                source TEXT,
                priority INTEGER,
                status TEXT,
                queued_at TEXT,
                processed_at TEXT,
                completed_at TEXT,
                result TEXT,
                result_verified INTEGER,
                verification_notes TEXT,
                ctrm_coherent REAL,
                ctrm_authentic REAL,
                ctrm_actionable REAL,
                ctrm_meaningful REAL,
                ctrm_grounded REAL,
                ctrm_confidence REAL
            )
        """)
    return db_path

class TestCTRMPromptManager:
    def test_init(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        assert manager.db_path == temp_db

    def test_calculate_ctrm_scores(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        prompt = "Implement a test for Ouroboros in /tests/core/test_ouroboros.py"
        scores = manager._calculate_ctrm_scores(prompt)
        
        assert "coherent" in scores
        assert "authentic" in scores
        assert "actionable" in scores
        assert "meaningful" in scores
        assert "grounded" in scores
        assert "confidence" in scores
        
        # This prompt is fairly grounded and actionable
        assert scores["grounded"] >= 0.6
        assert scores["actionable"] >= 0.6

    def test_enqueue(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        prompt = "New prompt"
        prompt_id = manager.enqueue(prompt, priority=2, source="test_source")
        
        assert prompt_id.startswith("prompt_")
        
        with sqlite3.connect(temp_db) as conn:
            row = conn.execute("SELECT id, prompt, source, priority, status FROM prompt_queue").fetchone()
            assert row[0] == prompt_id
            assert row[1] == prompt
            assert row[2] == "test_source"
            assert row[3] == 2
            assert row[4] == "pending"

    def test_dequeue(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        manager.enqueue("High priority", priority=1)
        manager.enqueue("Low priority", priority=10)
        
        # Test dequeue ordering
        prompts = manager.dequeue(limit=2)
        assert len(prompts) == 2
        assert prompts[0]["prompt"] == "High priority"
        assert prompts[1]["prompt"] == "Low priority"

    def test_mark_processing(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        prompt_id = manager.enqueue("Test prompt")
        
        success = manager.mark_processing(prompt_id)
        assert success is True
        
        with sqlite3.connect(temp_db) as conn:
            row = conn.execute("SELECT status, processed_at FROM prompt_queue WHERE id = ?", (prompt_id,)).fetchone()
            assert row[0] == "processing"
            assert row[1] is not None

    def test_complete(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        prompt_id = manager.enqueue("Test prompt")
        manager.mark_processing(prompt_id)
        
        success = manager.complete(prompt_id, "The result content", verified=True, notes="Excellent result")
        assert success is True
        
        with sqlite3.connect(temp_db) as conn:
            row = conn.execute("SELECT status, result, result_verified, verification_notes FROM prompt_queue WHERE id = ?", (prompt_id,)).fetchone()
            assert row[0] == "completed"
            assert row[1] == "The result content"
            assert row[2] == 1
            assert row[3] == "Excellent result"

    def test_get_stats(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        manager.enqueue("P1")
        manager.enqueue("P2")
        p3 = manager.enqueue("P3")
        manager.mark_processing(p3)
        p4 = manager.enqueue("P4")
        manager.mark_processing(p4)
        manager.complete(p4, "done")
        
        stats = manager.get_stats()
        assert stats["pending_count"] == 2
        assert stats["processing_count"] == 1
        assert stats["completed_count"] == 1
        assert "pending_avg_confidence" in stats

    @pytest.mark.asyncio
    async def test_process_next(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        prompt_id = manager.enqueue("Test process_next")
        
        # Mock bridge and followups
        manager.bridge = MagicMock()
        from src.ouroboros.core.queue_bridge import PromptResult
        manager.bridge.process_prompt_async = pytest.mark.asyncio(lambda *args, **kwargs: 
            asyncio.sleep(0) or PromptResult(success=True, content="Result", provider="test", error=None, wait_time_ms=0))
        
        # Actual implementation of process_next uses await manager.bridge.process_prompt_async
        # We need to mock it properly as an AsyncMock
        from unittest.mock import AsyncMock
        manager.bridge.process_prompt_async = AsyncMock(return_value=PromptResult(
            success=True, content="Result", provider="test", error=None, wait_time_ms=0
        ))
        
        result = await manager.process_next()
        
        assert result["prompt_id"] == prompt_id
        assert result["result"].content == "Result"
        assert manager.bridge.process_prompt_async.called
        
        with sqlite3.connect(temp_db) as conn:
            row = conn.execute("SELECT status, result FROM prompt_queue WHERE id = ?", (prompt_id,)).fetchone()
            assert row[0] == "completed"
            assert row[1] == "Result"

    def test_get_connection(self, temp_db):
        manager = CTRMPromptManager(temp_db)
        conn = manager._get_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()
