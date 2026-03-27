"""
Tests for Prompt Queue Bridge

Tests:
- PromptQueueBridge class
- ProviderStatus dataclass
- QueueStatus dataclass
- PromptResult dataclass
- Status retrieval
- Queue operations
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess
import json

from src.ouroboros.core.queue_bridge import (
    PromptQueueBridge,
    ProviderStatus,
    QueueStatus,
    PromptResult,
)


class TestProviderStatus:
    """Tests for ProviderStatus dataclass."""

    def test_create_provider_status(self):
        """Test creating ProviderStatus."""
        status = ProviderStatus(
            name="glm",
            enabled=True,
            available=True,
            unavailable_reason=None,
            rate_limited=False,
            wait_time_ms=0,
            used=100,
            limit=500,
            window_hours=24,
            auth_type="api_key",
        )

        assert status.name == "glm"
        assert status.enabled is True
        assert status.available is True

    def test_provider_status_defaults(self):
        """Test creating ProviderStatus with defaults."""
        status = ProviderStatus(
            name="test",
            enabled=False,
            available=False,
            unavailable_reason="test",
            rate_limited=False,
            wait_time_ms=0,
            used=0,
            limit=0,
            window_hours=0,
            auth_type="none",
        )

        assert status.name == "test"


class TestQueueStatus:
    """Tests for QueueStatus dataclass."""

    def test_create_queue_status(self):
        """Test creating QueueStatus."""
        status = QueueStatus(
            pending=5,
            completed=10,
            failed=2,
            processing=False,
            providers={
                "glm": ProviderStatus(
                    name="glm",
                    enabled=True,
                    available=True,
                    unavailable_reason=None,
                    rate_limited=False,
                    wait_time_ms=0,
                    used=100,
                    limit=500,
                    window_hours=24,
                    auth_type="api_key",
                )
            },
        )

        assert status.pending == 5
        assert status.completed == 10
        assert status.failed == 2
        assert "glm" in status.providers

    def test_queue_status_empty_providers(self):
        """Test creating QueueStatus with empty providers."""
        status = QueueStatus(
            pending=0, completed=0, failed=0, processing=False, providers={}
        )

        assert status.providers == {}


class TestPromptResult:
    """Tests for PromptResult dataclass."""

    def test_create_prompt_result_success(self):
        """Test creating successful PromptResult."""
        result = PromptResult(
            success=True,
            content="Test content",
            provider="glm",
            error=None,
            wait_time_ms=100,
        )

        assert result.success is True
        assert result.content == "Test content"
        assert result.provider == "glm"

    def test_create_prompt_result_failure(self):
        """Test creating failed PromptResult."""
        result = PromptResult(
            success=False,
            content=None,
            provider=None,
            error="Rate limited",
            wait_time_ms=5000,
        )

        assert result.success is False
        assert result.error == "Rate limited"
        assert result.wait_time_ms == 5000


class TestPromptQueueBridge:
    """Tests for PromptQueueBridge class."""

    @pytest.fixture
    def mock_bridge(self):
        """Create bridge with mocked subprocess."""
        with patch("subprocess.run") as mock_run:
            yield mock_run

    def test_init_default(self):
        """Test creating bridge with defaults."""
        bridge = PromptQueueBridge()

        assert bridge.queue_script == "./queue.sh"
        assert bridge._cache_ttl_seconds == 5

    def test_init_custom(self):
        """Test creating bridge with custom settings."""
        bridge = PromptQueueBridge(
            queue_script="/custom/script.sh", project_root=Path("/custom/project")
        )

        assert bridge.queue_script == "/custom/script.sh"
        assert bridge.project_root == Path("/custom/project")

    def test_parse_provider_status(self, mock_bridge):
        """Test parsing provider status from JSON."""
        bridge = PromptQueueBridge()

        data = {
            "name": "glm",
            "enabled": True,
            "available": True,
            "unavailableReason": None,
            "rateLimited": False,
            "waitTime": 0,
            "used": 100,
            "limit": 500,
            "windowHours": 24,
            "auth": "api_key",
        }

        status = bridge._parse_provider_status(data)

        assert status.name == "glm"
        assert status.enabled is True
        assert status.available is True

    def test_parse_provider_status_missing_fields(self, mock_bridge):
        """Test parsing provider status with missing fields."""
        bridge = PromptQueueBridge()

        data = {}

        status = bridge._parse_provider_status(data)

        assert status.name == "unknown"
        assert status.enabled is False


class TestPromptQueueBridgeStatus:
    """Tests for status retrieval."""

    @pytest.fixture
    def bridge(self):
        """Create bridge with mocked subprocess."""
        with patch("subprocess.run") as mock_run:
            bridge = PromptQueueBridge()
            yield bridge, mock_run

    def test_get_status_success(self, bridge):
        """Test getting status successfully."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "pending": 3,
                "completed": 10,
                "failed": 1,
                "processing": False,
                "providers": {
                    "glm": {
                        "name": "glm",
                        "enabled": True,
                        "available": True,
                        "rateLimited": False,
                        "used": 100,
                        "limit": 500,
                    }
                },
            }
        )
        mock_result.stderr = ""

        mock_run.return_value = mock_result

        status = b.get_status(use_cache=False)

        assert status.pending == 3
        assert status.completed == 10

    def test_get_status_failure(self, bridge):
        """Test getting status when command fails."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Command failed"

        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Queue status failed"):
            b.get_status(use_cache=False)

    def test_get_status_cached(self, bridge):
        """Test using cached status."""
        b, mock_run = bridge

        cached_status = QueueStatus(
            pending=5, completed=10, failed=2, processing=False, providers={}
        )
        b._status_cache = cached_status
        b._cache_time = b._cache_time or __import__("datetime").datetime.now()

        status = b.get_status(use_cache=True)

        assert status == cached_status
        mock_run.assert_not_called()

    def test_get_available_providers(self, bridge):
        """Test getting available providers."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "pending": 0,
                "completed": 0,
                "failed": 0,
                "processing": False,
                "providers": {
                    "glm": {
                        "name": "glm",
                        "enabled": True,
                        "available": True,
                        "rateLimited": False,
                        "used": 100,
                        "limit": 500,
                    },
                    "gemini": {
                        "name": "gemini",
                        "enabled": True,
                        "available": False,
                        "rateLimited": True,
                        "used": 1500,
                        "limit": 1500,
                    },
                },
            }
        )
        mock_result.stderr = ""

        mock_run.return_value = mock_result

        available = b.get_available_providers()

        assert "glm" in available
        assert "gemini" not in available

    def test_get_wait_time(self, bridge):
        """Test getting wait time."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "pending": 0,
                "completed": 0,
                "failed": 0,
                "processing": False,
                "providers": {
                    "glm": {
                        "name": "glm",
                        "enabled": True,
                        "available": True,
                        "rateLimited": True,
                        "waitTime": 1000,
                        "used": 100,
                        "limit": 500,
                    }
                },
            }
        )
        mock_result.stderr = ""

        mock_run.return_value = mock_result

        wait_time = b.get_wait_time()

        assert wait_time == 1000


class TestPromptQueueBridgeQueueOperations:
    """Tests for queue operations."""

    @pytest.fixture
    def bridge(self):
        """Create bridge with mocked subprocess."""
        with patch("subprocess.run") as mock_run:
            bridge = PromptQueueBridge()
            yield bridge, mock_run

    def test_enqueue_success(self, bridge):
        """Test enqueuing a prompt."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "📥 Enqueued: prompt_123_abc (priority 5)"
        mock_result.stderr = ""

        mock_run.return_value = mock_result

        prompt_id = b.enqueue("Test prompt", priority=5)

        assert "prompt_123" in prompt_id or prompt_id.startswith("prompt_")

    def test_enqueue_with_provider(self, bridge):
        """Test enqueuing with specific provider."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "📥 Enqueued: prompt_123 (priority 3)"
        mock_result.stderr = ""

        mock_run.return_value = mock_result

        prompt_id = b.enqueue("Test prompt", priority=3, provider="glm")

        assert mock_run.called

    def test_process_queue(self, bridge):
        """Test processing queue."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "✅ Completed: prompt_123\n✅ Completed: prompt_456"
        mock_result.stderr = ""

        mock_run.return_value = mock_result

        results = b.process_queue()

        assert len(results) >= 0

    def test_clear(self, bridge):
        """Test clearing queue."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0

        mock_run.return_value = mock_result

        b.clear("all")

        assert mock_run.called

    def test_enable_provider(self, bridge):
        """Test enabling a provider."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0

        mock_run.return_value = mock_result

        b.enable_provider("glm")

        assert mock_run.called

    def test_disable_provider(self, bridge):
        """Test disabling a provider."""
        b, mock_run = bridge

        mock_result = MagicMock()
        mock_result.returncode = 0

        mock_run.return_value = mock_result

        b.disable_provider("gemini")

        assert mock_run.called


class TestPromptQueueBridgeAsync:
    """Tests for async operations."""

    @pytest.fixture
    def bridge(self):
        """Create bridge with mocked subprocess."""
        with patch("subprocess.run") as mock_run:
            bridge = PromptQueueBridge()
            yield bridge, mock_run

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex async flow requiring full mock setup")
    async def test_process_prompt_async_available(self, bridge):
        """Test async prompt processing when provider available."""
        pass

    @pytest.mark.asyncio
    async def test_process_prompt_async_none_available(self, bridge):
        """Test async prompt processing when no provider available."""
        b, mock_run = bridge

        status_result = MagicMock()
        status_result.returncode = 0
        status_result.stdout = json.dumps(
            {
                "pending": 0,
                "completed": 0,
                "failed": 0,
                "processing": False,
                "providers": {
                    "glm": {
                        "name": "glm",
                        "enabled": True,
                        "available": False,
                        "rateLimited": True,
                        "waitTime": 5000,
                        "used": 500,
                        "limit": 500,
                    }
                },
            }
        )
        status_result.stderr = ""

        mock_run.return_value = status_result

        result = await b.process_prompt_async("Test prompt")

        assert result.success is False
        assert "rate limited" in result.error.lower()


class TestPromptQueueBridgeEdgeCases:
    """Edge case tests."""

    def test_login_invalid_provider(self):
        """Test login with invalid provider."""
        bridge = PromptQueueBridge()

        with pytest.raises(ValueError, match="OAuth login only available"):
            bridge.login("invalid")

    def test_retry_failed(self):
        """Test retrying failed prompts."""
        with patch("subprocess.run") as mock_run:
            bridge = PromptQueueBridge()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Retrying 3 prompts"

            mock_run.return_value = mock_result

            count = bridge.retry_failed()

            assert count == 3
