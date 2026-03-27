"""
Tests for Ouroboros API Server

Tests:
- OuroborosAPIServer class
- REST endpoints
- WebSocket handler
- State management
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
import json
import tempfile
import sqlite3

from src.ouroboros.core.api_server import OuroborosAPIServer


class TestOuroborosAPIServer:
    """Tests for OuroborosAPIServer class."""

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

        return db_path

    @pytest.fixture
    def server(self, temp_db):
        """Create server with test database."""
        with patch("ouroboros.core.api_server.CTRM_DB", temp_db):
            with patch("ouroboros.core.api_server.CTRMPromptManager"):
                with patch("ouroboros.core.api_server.PromptPrioritizer"):
                    with patch("ouroboros.core.api_server.PromptResponseAnalyzer"):
                        with patch("ouroboros.core.api_server.AutomatedPromptLoop"):
                            server = OuroborosAPIServer(port=8080)
                            return server

    def test_init_default(self):
        """Test creating server with defaults."""
        with patch("ouroboros.core.api_server.CTRMPromptManager"):
            with patch("ouroboros.core.api_server.PromptPrioritizer"):
                with patch("ouroboros.core.api_server.PromptResponseAnalyzer"):
                    with patch("ouroboros.core.api_server.AutomatedPromptLoop"):
                        server = OuroborosAPIServer()

                        assert server.port == 8080
                        assert server.manager is not None
                        assert server.prioritizer is not None
                        assert server.analyzer is not None
                        assert server.loop is not None
                        assert server.state["status"] == "running"
                        assert server.state["loop_active"] is False

    def test_init_custom_port(self):
        """Test creating server with custom port."""
        with patch("ouroboros.core.api_server.CTRMPromptManager"):
            with patch("ouroboros.core.api_server.PromptPrioritizer"):
                with patch("ouroboros.core.api_server.PromptResponseAnalyzer"):
                    with patch("ouroboros.core.api_server.AutomatedPromptLoop"):
                        server = OuroborosAPIServer(port=9000)

                        assert server.port == 9000

    def test_state_initialization(self):
        """Test initial state values."""
        with patch("ouroboros.core.api_server.CTRMPromptManager"):
            with patch("ouroboros.core.api_server.PromptPrioritizer"):
                with patch("ouroboros.core.api_server.PromptResponseAnalyzer"):
                    with patch("ouroboros.core.api_server.AutomatedPromptLoop"):
                        server = OuroborosAPIServer()

                        assert server.state["processed_count"] == 0
                        assert server.state["pending_count"] == 0
                        assert server.state["uptime_start"] is not None


class TestAPIEndpoints:
    """Tests for API endpoints."""

    @pytest.fixture
    def mock_server(self):
        """Create server with mocked dependencies."""
        with patch("ouroboros.core.api_server.CTRMPromptManager") as mock_manager:
            with patch(
                "ouroboros.core.api_server.PromptPrioritizer"
            ) as mock_prioritizer:
                with patch(
                    "ouroboros.core.api_server.PromptResponseAnalyzer"
                ) as mock_analyzer:
                    with patch(
                        "ouroboros.core.api_server.AutomatedPromptLoop"
                    ) as mock_loop:
                        mock_manager_instance = MagicMock()
                        mock_prioritizer_instance = MagicMock()
                        mock_analyzer_instance = MagicMock()
                        mock_loop_instance = MagicMock()

                        mock_manager.return_value = mock_manager_instance
                        mock_prioritizer.return_value = mock_prioritizer_instance
                        mock_analyzer.return_value = mock_analyzer_instance
                        mock_loop.return_value = mock_loop_instance

                        server = OuroborosAPIServer()
                        server.manager = mock_manager_instance
                        server.prioritizer = mock_prioritizer_instance
                        server.analyzer = mock_analyzer_instance
                        server.loop = mock_loop_instance

                        yield (
                            server,
                            mock_manager_instance,
                            mock_prioritizer_instance,
                            mock_analyzer_instance,
                        )

    @pytest.mark.asyncio
    async def test_get_prompts_empty(self, mock_server):
        """Test getting prompts when none available."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_prioritizer.get_next_prompt.return_value = []

        mock_request = MagicMock()
        mock_request.query.get.return_value = 10

        response = await server.get_prompts(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_prompts_with_data(self, mock_server):
        """Test getting prompts with data."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_prioritizer.get_next_prompt.return_value = [
            ({"id": "p1", "prompt": "Test", "priority": 5, "ctrm_confidence": 0.8}, 0.9)
        ]

        mock_request = MagicMock()
        mock_request.query.get.return_value = 10

        response = await server.get_prompts(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_server):
        """Test getting stats."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_manager.get_stats.return_value = {
            "completed_count": 10,
            "pending_count": 5,
            "processing_count": 2,
        }
        mock_analyzer.get_summary.return_value = {"by_quality": {"complete": 5}}

        mock_request = MagicMock()

        response = await server.get_stats(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_completed(self, mock_server):
        """Test getting completed prompts."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_analysis = MagicMock()
        mock_analysis.prompt_id = "c1"
        mock_analysis.prompt = "Test prompt"
        mock_analysis.quality.value = "complete"
        mock_analysis.confidence = 0.85
        mock_analysis.needs_followup = False
        mock_analysis.suggested_prompts = []
        mock_analysis.analysis_timestamp = "2025-01-01"

        mock_analyzer.analyze_all_completed.return_value = [mock_analysis]

        mock_request = MagicMock()
        mock_request.query.get.return_value = 10

        response = await server.get_completed(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_add_prompt_success(self, mock_server):
        """Test adding a prompt successfully."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_manager.enqueue.return_value = "new-prompt-123"

        mock_request = MagicMock()
        mock_request.json = AsyncMock(
            return_value={"prompt": "New test prompt", "priority": 7, "source": "test"}
        )

        response = await server.add_prompt(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_add_prompt_empty(self, mock_server):
        """Test adding empty prompt returns error."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"prompt": ""})

        response = await server.add_prompt(mock_request)

        assert response.status == 400

    @pytest.mark.asyncio
    async def test_analyze_prompt_found(self, mock_server):
        """Test analyzing existing prompt."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_analysis = MagicMock()
        mock_analysis.prompt_id = "a1"
        mock_analysis.prompt = "Test prompt"
        mock_analysis.quality.value = "complete"
        mock_analysis.confidence = 0.85
        mock_analysis.success_indicators = ["done"]
        mock_analysis.failure_indicators = []
        mock_analysis.incomplete_indicators = []
        mock_analysis.actions_taken = []
        mock_analysis.needs_followup = False
        mock_analysis.followup_reason = ""
        mock_analysis.suggested_prompts = []

        mock_analyzer.analyze_response.return_value = mock_analysis

        mock_request = MagicMock()
        mock_request.match_info = {"id": "a1"}

        response = await server.analyze_prompt(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_analyze_prompt_not_found(self, mock_server):
        """Test analyzing non-existent prompt."""
        server, mock_manager, mock_prioritizer, mock_analyzer = mock_server

        mock_analyzer.analyze_response.return_value = None

        mock_request = MagicMock()
        mock_request.match_info = {"id": "nonexistent"}

        response = await server.analyze_prompt(mock_request)

        assert response.status == 404


class TestControlActions:
    """Tests for control actions."""

    @pytest.fixture
    def mock_server(self):
        """Create server with mocked dependencies."""
        with patch("ouroboros.core.api_server.CTRMPromptManager") as mock_manager:
            with patch(
                "ouroboros.core.api_server.PromptPrioritizer"
            ) as mock_prioritizer:
                with patch(
                    "ouroboros.core.api_server.PromptResponseAnalyzer"
                ) as mock_analyzer:
                    with patch(
                        "ouroboros.core.api_server.AutomatedPromptLoop"
                    ) as mock_loop:
                        mock_manager_instance = MagicMock()
                        mock_prioritizer_instance = MagicMock()
                        mock_analyzer_instance = MagicMock()
                        mock_loop_instance = MagicMock()

                        mock_manager.return_value = mock_manager_instance
                        mock_prioritizer.return_value = mock_prioritizer_instance
                        mock_analyzer.return_value = mock_analyzer_instance
                        mock_loop.return_value = mock_loop_instance

                        server = OuroborosAPIServer()
                        server.manager = mock_manager_instance
                        server.prioritizer = mock_prioritizer_instance
                        server.analyzer = mock_analyzer_instance
                        server.loop = mock_loop_instance

                        yield server, mock_loop_instance

    @pytest.mark.asyncio
    async def test_control_start_loop(self, mock_server):
        """Test starting the loop."""
        server, mock_loop = mock_server

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"action": "start_loop"})

        response = await server.control_action(mock_request)

        assert response.status == 200
        assert server.state["loop_active"] is True

    @pytest.mark.asyncio
    async def test_control_pause_loop(self, mock_server):
        """Test pausing the loop."""
        server, mock_loop = mock_server

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"action": "pause_loop"})

        response = await server.control_action(mock_request)

        assert response.status == 200
        assert server.state["loop_active"] is False
        assert server.state["status"] == "paused"

    @pytest.mark.asyncio
    async def test_control_run_once(self, mock_server):
        """Test running loop once."""
        server, mock_loop = mock_server

        mock_loop.run_once = AsyncMock(return_value={"success": True})

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"action": "run_once"})

        response = await server.control_action(mock_request)

        assert response.status == 200
        assert server.state["processed_count"] == 1

    @pytest.mark.asyncio
    async def test_control_emergency_stop(self, mock_server):
        """Test emergency stop."""
        server, mock_loop = mock_server

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"action": "emergency_stop"})

        response = await server.control_action(mock_request)

        assert response.status == 200
        assert server.state["loop_active"] is False
        assert server.state["status"] == "stopped"


class TestWebSocket:
    """Tests for WebSocket functionality."""

    @pytest.fixture
    def mock_server(self):
        """Create server with mocked dependencies."""
        with patch("ouroboros.core.api_server.CTRMPromptManager"):
            with patch("ouroboros.core.api_server.PromptPrioritizer"):
                with patch("ouroboros.core.api_server.PromptResponseAnalyzer"):
                    with patch("ouroboros.core.api_server.AutomatedPromptLoop"):
                        server = OuroborosAPIServer()
                        yield server

    @pytest.mark.asyncio
    async def test_websocket_handler(self, mock_server):
        """Test WebSocket connection."""
        pass

    @pytest.mark.asyncio
    async def test_broadcast_state(self, mock_server):
        """Test broadcasting state to websockets."""
        pass

    @pytest.mark.asyncio
    async def test_broadcast_state_no_clients(self, mock_server):
        """Test broadcasting with no connected clients."""
        mock_server.websockets.clear()

        await mock_server.broadcast_state()


class TestProviderStatus:
    """Tests for provider status."""

    def test_get_provider_status(self):
        """Test provider status returns expected structure."""
        with patch("ouroboros.core.api_server.CTRMPromptManager"):
            with patch("ouroboros.core.api_server.PromptPrioritizer"):
                with patch("ouroboros.core.api_server.PromptResponseAnalyzer"):
                    with patch("ouroboros.core.api_server.AutomatedPromptLoop"):
                        server = OuroborosAPIServer()

                        status = server._get_provider_status()

                        assert "glm" in status
                        assert "gemini" in status
                        assert "claude" in status
                        assert "local" in status
                        assert "available" in status["glm"]
                        assert "used" in status["glm"]
                        assert "limit" in status["glm"]
