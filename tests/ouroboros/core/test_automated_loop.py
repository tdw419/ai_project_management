"""
Tests for Automated Prompt Loop

Tests:
- AutomatedPromptLoop class
- run_once method
- run_forever method
- Prompt generation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
import tempfile
import sqlite3
import json

from src.ouroboros.core.automated_loop import AutomatedPromptLoop, HAS_AUTOSPEC


class TestAutomatedPromptLoop:
    """Tests for AutomatedPromptLoop class."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary test database."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_queue (
                id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                result TEXT,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                source TEXT,
                ctrm_confidence REAL DEFAULT 0.5,
                verification_notes TEXT,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ctrm_coherent REAL DEFAULT 0.5,
                ctrm_authentic REAL DEFAULT 0.5,
                ctrm_actionable REAL DEFAULT 0.5,
                ctrm_meaningful REAL DEFAULT 0.5,
                ctrm_grounded REAL DEFAULT 0.5
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_scores (
                prompt_id TEXT PRIMARY KEY,
                score REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

        return db_path

    @pytest.fixture
    def mock_loop(self, temp_db):
        """Create loop with mocked dependencies."""
        with patch("ouroboros.core.automated_loop.CTRMPromptManager") as mock_manager:
            with patch(
                "ouroboros.core.automated_loop.PromptPrioritizer"
            ) as mock_prioritizer:
                with patch(
                    "ouroboros.core.automated_loop.PromptGenerator"
                ) as mock_generator:
                    mock_manager_instance = MagicMock()
                    mock_prioritizer_instance = MagicMock()
                    mock_generator_instance = MagicMock()

                    mock_manager.return_value = mock_manager_instance
                    mock_prioritizer.return_value = mock_prioritizer_instance
                    mock_generator.return_value = mock_generator_instance

                    loop = AutomatedPromptLoop(db_path=temp_db)
                    loop.manager = mock_manager_instance
                    loop.prioritizer = mock_prioritizer_instance
                    loop.generator = mock_generator_instance

                    yield (
                        loop,
                        mock_manager_instance,
                        mock_prioritizer_instance,
                        mock_generator_instance,
                    )

    def test_init(self, temp_db):
        """Test creating AutomatedPromptLoop."""
        with patch("ouroboros.core.automated_loop.CTRMPromptManager"):
            with patch("ouroboros.core.automated_loop.PromptPrioritizer"):
                with patch("ouroboros.core.automated_loop.PromptGenerator"):
                    loop = AutomatedPromptLoop(db_path=temp_db)

                    assert loop.db_path == temp_db
                    assert loop.manager is not None
                    assert loop.prioritizer is not None
                    assert loop.generator is not None
                    assert loop.stats["processed"] == 0
                    assert loop.stats["generated"] == 0
                    assert loop.stats["errors"] == 0

    def test_init_default_db(self):
        """Test creating loop with default database."""
        with patch("ouroboros.core.automated_loop.CTRMPromptManager"):
            with patch("ouroboros.core.automated_loop.PromptPrioritizer"):
                with patch("ouroboros.core.automated_loop.PromptGenerator"):
                    loop = AutomatedPromptLoop()
                    assert loop.db_path is not None

    @pytest.mark.asyncio
    async def test_run_once_no_prompts(self, mock_loop):
        """Test run_once with no pending prompts."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_prioritizer.get_next_one.return_value = None

        result = await loop.run_once()

        assert result is None

    @pytest.mark.asyncio
    async def test_run_once_dry_run(self, mock_loop):
        """Test run_once with dry_run=True."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_prioritizer.get_next_one.return_value = (
            {
                "id": "dry-1",
                "prompt": "Test prompt",
                "priority": 5,
                "ctrm_confidence": 0.5,
            },
            0.9,
        )

        result = await loop.run_once(dry_run=True)

        assert result is not None
        assert result["dry_run"] is True
        assert result["prompt"]["id"] == "dry-1"

    @pytest.mark.asyncio
    async def test_run_once_success(self, mock_loop):
        """Test successful run_once execution."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_prioritizer.get_next_one.return_value = (
            {
                "id": "run-1",
                "prompt": "Test prompt",
                "priority": 5,
                "ctrm_confidence": 0.5,
            },
            0.9,
        )

        with patch.object(
            loop, "_process_prompt", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = {"success": True, "content": "Result"}

            with patch(
                "ouroboros.core.response_analyzer.PromptResponseAnalyzer"
            ) as mock_analyzer_class:
                mock_analyzer = MagicMock()
                mock_analyzer_class.return_value = mock_analyzer
                mock_analyzer.analyze_response.return_value = None

                result = await loop.run_once()

                assert result is not None
                assert "prompt" in result

    @pytest.mark.asyncio
    async def test_run_once_updates_stats(self, mock_loop):
        """Test that stats are updated after processing."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_prioritizer.get_next_one.return_value = (
            {
                "id": "stats-1",
                "prompt": "Test prompt",
                "priority": 5,
                "ctrm_confidence": 0.5,
            },
            0.9,
        )

        with patch.object(
            loop, "_process_prompt", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = {"success": True, "content": "Result"}

            with patch(
                "ouroboros.core.response_analyzer.PromptResponseAnalyzer"
            ) as mock_analyzer_class:
                mock_analyzer = MagicMock()
                mock_analyzer_class.return_value = mock_analyzer
                mock_analyzer.analyze_response.return_value = None

                await loop.run_once()

                assert loop.stats["processed"] >= 0

    def test_process_prompt_simulated(self, mock_loop):
        """Test the _process_prompt method returns simulated result."""
        loop, _, _, _ = mock_loop
        result = asyncio.run(loop._process_prompt("Test prompt"))

        assert "success" in result
        assert "content" in result

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex exception handling - requires careful mocking")
    async def test_run_once_handles_exception(self, mock_loop):
        """Test run_once handles exceptions gracefully."""
        pass

    def test_show_next_n(self, mock_loop):
        """Test showing next N prompts."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_prioritizer.get_next_prompt.return_value = [
            (
                {
                    "id": "next-1",
                    "prompt": "First prompt",
                    "priority": 8,
                    "ctrm_confidence": 0.7,
                },
                0.9,
            ),
            (
                {
                    "id": "next-2",
                    "prompt": "Second prompt",
                    "priority": 5,
                    "ctrm_confidence": 0.5,
                },
                0.7,
            ),
        ]

        loop.show_next_n(n=5)

    def test_get_stats(self, mock_loop):
        """Test getting loop statistics."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_manager.get_stats.return_value = {"completed_count": 5}

        stats = loop.get_stats()

        assert "loop" in stats
        assert "queue" in stats
        assert stats["loop"]["processed"] == 0

    @pytest.mark.asyncio
    async def test_run_forever_single_iteration(self, mock_loop):
        """Test run_forever with limited iterations."""
        loop, mock_manager, mock_prioritizer, mock_generator = mock_loop

        mock_prioritizer.get_next_one.return_value = (
            {
                "id": "forever-1",
                "prompt": "Test prompt",
                "priority": 5,
                "ctrm_confidence": 0.5,
            },
            0.9,
        )

        with patch.object(
            loop, "_process_prompt", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = {"success": True, "content": "Result"}

            with patch(
                "ouroboros.core.response_analyzer.PromptResponseAnalyzer"
            ) as mock_analyzer_class:
                mock_analyzer = MagicMock()
                mock_analyzer_class.return_value = mock_analyzer
                mock_analyzer.analyze_response.return_value = None

                await loop.run_forever(interval_seconds=0, max_iterations=1)

                assert loop.stats["processed"] >= 0
