"""
Tests for Prompt Response Analyzer

Tests:
- ResponseQuality enum
- AnalysisResult dataclass
- PromptResponseAnalyzer class
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import sqlite3
import json

from src.ouroboros.core.response_analyzer import (
    ResponseQuality,
    AnalysisResult,
    PromptResponseAnalyzer,
)


class TestResponseQuality:
    """Tests for ResponseQuality enum."""

    def test_enum_values(self):
        """Test all enum values exist."""
        assert ResponseQuality.COMPLETE.value == "complete"
        assert ResponseQuality.PARTIAL.value == "partial"
        assert ResponseQuality.FAILED.value == "failed"
        assert ResponseQuality.UNCLEAR.value == "unclear"
        assert ResponseQuality.NEEDS_REVIEW.value == "needs_review"


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_create_analysis_result(self):
        """Test creating an AnalysisResult."""
        result = AnalysisResult(
            prompt_id="test-123",
            prompt="Test prompt",
            result="Test result",
            quality=ResponseQuality.COMPLETE,
            confidence=0.85,
            success_indicators=["completed", "done"],
            failure_indicators=[],
            incomplete_indicators=[],
            actions_taken=["file_created: test.py"],
            needs_followup=False,
            followup_reason="Task appears complete",
            suggested_prompts=[],
            analysis_timestamp="2025-01-01T00:00:00",
        )

        assert result.prompt_id == "test-123"
        assert result.quality == ResponseQuality.COMPLETE
        assert result.confidence == 0.85
        assert result.needs_followup is False


class TestPromptResponseAnalyzer:
    """Tests for PromptResponseAnalyzer class."""

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
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ctrm_coherent REAL DEFAULT 0.5,
                ctrm_authentic REAL DEFAULT 0.5,
                ctrm_actionable REAL DEFAULT 0.5,
                ctrm_meaningful REAL DEFAULT 0.5,
                ctrm_grounded REAL DEFAULT 0.5
            )
        """)

        conn.commit()
        conn.close()

        return db_path

    @pytest.fixture
    def analyzer(self, temp_db):
        """Create analyzer with test database."""
        return PromptResponseAnalyzer(db_path=temp_db)

    def test_init_default(self):
        """Test creating analyzer with default db path."""
        analyzer = PromptResponseAnalyzer()
        assert analyzer.db_path is not None
        assert len(analyzer.success_patterns) > 0
        assert len(analyzer.failure_patterns) > 0
        assert len(analyzer.incomplete_patterns) > 0

    def test_init_custom_db(self, temp_db):
        """Test creating analyzer with custom db path."""
        analyzer = PromptResponseAnalyzer(db_path=temp_db)
        assert analyzer.db_path == temp_db

    def test_analyze_response_not_found(self, analyzer):
        """Test analyzing a non-existent prompt."""
        result = analyzer.analyze_response("non-existent-id")
        assert result is None

    def test_analyze_response_success_indicators(self, analyzer, temp_db):
        """Test analyzing a successful response."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                "success-1",
                "Fix the bug",
                "Task completed successfully. All tests passed.",
                "completed",
                0.8,
            ),
        )

        conn.commit()
        conn.close()

        result = analyzer.analyze_response("success-1")

        assert result is not None
        assert result.prompt_id == "success-1"
        assert result.quality in [
            ResponseQuality.COMPLETE,
            ResponseQuality.NEEDS_REVIEW,
        ]
        assert len(result.success_indicators) > 0

    def test_analyze_response_failure_indicators(self, analyzer, temp_db):
        """Test analyzing a failed response."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                "fail-1",
                "Fix the bug",
                "Error: Cannot complete task. Failed.",
                "completed",
                0.3,
            ),
        )

        conn.commit()
        conn.close()

        result = analyzer.analyze_response("fail-1")

        assert result is not None
        assert result.quality in [ResponseQuality.FAILED, ResponseQuality.PARTIAL]
        assert len(result.failure_indicators) > 0
        assert result.needs_followup is True

    def test_analyze_response_incomplete_indicators(self, analyzer, temp_db):
        """Test analyzing a partial response."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                "partial-1",
                "Implement feature",
                "Work in progress. TODO: Add tests.",
                "completed",
                0.5,
            ),
        )

        conn.commit()
        conn.close()

        result = analyzer.analyze_response("partial-1")

        assert result is not None
        assert result.quality in [ResponseQuality.PARTIAL, ResponseQuality.NEEDS_REVIEW]
        assert len(result.incomplete_indicators) > 0

    def test_analyze_response_action_patterns(self, analyzer, temp_db):
        """Test that action patterns are detected."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                "action-1",
                "Create file",
                "Created the file test.py and added the function.",
                "completed",
                0.7,
            ),
        )

        conn.commit()
        conn.close()

        result = analyzer.analyze_response("action-1")

        assert result is not None
        assert len(result.actions_taken) > 0

    def test_determine_quality_complete(self, analyzer):
        """Test quality determination for complete responses."""
        quality, confidence = analyzer._determine_quality(
            success=["completed", "done"],
            failure=[],
            incomplete=[],
            actions=["file_created: test.py"],
        )

        assert quality == ResponseQuality.COMPLETE
        assert confidence == 0.85

    def test_determine_quality_failed(self, analyzer):
        """Test quality determination for failed responses."""
        quality, confidence = analyzer._determine_quality(
            success=[], failure=["error", "failed"], incomplete=[], actions=[]
        )

        assert quality == ResponseQuality.FAILED
        assert confidence == 0.9

    def test_determine_quality_partial(self, analyzer):
        """Test quality determination for partial responses."""
        quality, confidence = analyzer._determine_quality(
            success=[], failure=[], incomplete=["TODO", "FIXME", "partial"], actions=[]
        )

        assert quality == ResponseQuality.PARTIAL
        assert confidence == 0.7

    def test_needs_followup_failed(self, analyzer):
        """Test follow-up detection for failed tasks."""
        needs, reason = analyzer._needs_followup(
            ResponseQuality.FAILED, failure=["error"], incomplete=[], actions=[]
        )

        assert needs is True
        assert "failed" in reason.lower()

    def test_needs_followup_complete(self, analyzer):
        """Test follow-up detection for complete tasks."""
        needs, reason = analyzer._needs_followup(
            ResponseQuality.COMPLETE,
            failure=[],
            incomplete=[],
            actions=["file_created: test.py"],
        )

        assert needs is False

    def test_generate_followups_failed(self, analyzer):
        """Test follow-up generation for failed tasks."""
        followups = analyzer._generate_followups(
            prompt="Debug and fix the issue",
            result="Error occurred",
            quality=ResponseQuality.FAILED,
            failure=["error"],
            incomplete=[],
            actions=[],
        )

        assert len(followups) > 0
        assert any("debug" in f.lower() or "fix" in f.lower() for f in followups)

    def test_generate_followups_partial(self, analyzer):
        """Test follow-up generation for partial tasks."""
        followups = analyzer._generate_followups(
            prompt="Implement the feature",
            result="Partial implementation",
            quality=ResponseQuality.PARTIAL,
            failure=[],
            incomplete=["TODO"],
            actions=[],
        )

        assert len(followups) > 0

    def test_generate_followups_test_needed(self, analyzer):
        """Test follow-up generation when implementation is done but no docs."""
        followups = analyzer._generate_followups(
            prompt="Implement the login feature",
            result="Login feature implemented and working",
            quality=ResponseQuality.COMPLETE,
            failure=[],
            incomplete=[],
            actions=["feature_added: login"],
        )

        assert len(followups) > 0

    def test_analyze_all_completed_empty(self, analyzer, temp_db):
        """Test analyzing when no completed prompts exist."""
        results = analyzer.analyze_all_completed(limit=10)
        assert results == []

    def test_analyze_all_completed_with_data(self, analyzer, temp_db):
        """Test analyzing multiple completed prompts."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("comp-1", "Task 1", "Done", "completed", 0.8),
        )
        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("comp-2", "Task 2", "Failed", "completed", 0.3),
        )

        conn.commit()
        conn.close()

        results = analyzer.analyze_all_completed(limit=10)

        assert len(results) == 2

    def test_get_summary_empty(self, analyzer):
        """Test get_summary with no data."""
        summary = analyzer.get_summary()

        assert "total_analyzed" in summary or "total" in summary

    def test_get_summary_with_data(self, analyzer, temp_db):
        """Test get_summary with analyzed data."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("sum-1", "Task 1", "Completed successfully", "completed", 0.8),
        )
        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("sum-2", "Task 2", "Failed", "completed", 0.3),
        )

        conn.commit()
        conn.close()

        summary = analyzer.get_summary()

        assert summary["total_analyzed"] == 2

    def test_store_analysis(self, analyzer, temp_db):
        """Test storing analysis to database."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("store-1", "Task", "Result", "completed", 0.5),
        )

        conn.commit()
        conn.close()

        analysis = AnalysisResult(
            prompt_id="store-1",
            prompt="Task",
            result="Result",
            quality=ResponseQuality.COMPLETE,
            confidence=0.85,
            success_indicators=["done"],
            failure_indicators=[],
            incomplete_indicators=[],
            actions_taken=[],
            needs_followup=False,
            followup_reason="Complete",
            suggested_prompts=[],
            analysis_timestamp="2025-01-01T00:00:00",
        )

        analyzer.store_analysis(analysis)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT verification_notes FROM prompt_queue WHERE id = ?", ("store-1",)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert "complete" in row[0].lower()

    def test_enqueue_followups(self, analyzer, temp_db):
        """Test enqueuing follow-up prompts."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO prompt_queue (id, prompt, result, status, priority, ctrm_confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            ("parent-1", "Task", "Done", "completed", 5, 0.8),
        )

        conn.commit()
        conn.close()

        analysis = AnalysisResult(
            prompt_id="parent-1",
            prompt="Task",
            result="Done",
            quality=ResponseQuality.COMPLETE,
            confidence=0.85,
            success_indicators=["done"],
            failure_indicators=[],
            incomplete_indicators=[],
            actions_taken=[],
            needs_followup=True,
            followup_reason="Verify results",
            suggested_prompts=["Verify the implementation"],
            analysis_timestamp="2025-01-01T00:00:00",
        )

        count = analyzer.enqueue_followups(analysis)

        assert count == 1

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT prompt, source FROM prompt_queue WHERE source LIKE 'analysis:%'"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert "Verify" in row[0]
