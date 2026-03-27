import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from ouroboros.core.unified_prompt_engine import (
    PromptTemplate, PromptCategory, PromptRegistry, 
    PromptOutcome, ContextProvider, UnifiedPromptEngine,
    create_default_engine
)
from ouroboros.core.queue_bridge import PromptResult

@pytest.fixture
def temp_registry_path(tmp_path):
    return tmp_path / "registry.json"

class TestPromptTemplate:
    def test_render_success(self):
        template = PromptTemplate(
            id="test", version=1, category=PromptCategory.ANALYSIS,
            description="test", template="Hello {name}!", variables=["name"]
        )
        assert template.render(name="World") == "Hello World!"

    def test_render_default(self):
        template = PromptTemplate(
            id="test", version=1, category=PromptCategory.ANALYSIS,
            description="test", template="Hello {name}!", 
            variables=["name"], defaults={"name": "Default"}
        )
        assert template.render() == "Hello Default!"

    def test_render_missing_var(self):
        template = PromptTemplate(
            id="test", version=1, category=PromptCategory.ANALYSIS,
            description="test", template="Hello {name}!", variables=["name"]
        )
        with pytest.raises(ValueError, match="Missing required variables"):
            template.render()

class TestPromptRegistry:
    def test_register_and_get(self, temp_registry_path):
        registry = PromptRegistry(temp_registry_path)
        template = PromptTemplate(
            id="t1", version=1, category=PromptCategory.HYPOTHESIS,
            description="d", template="t", variables=[]
        )
        registry.register(template)
        
        assert registry.get("t1:v1") == template
        assert registry.get_latest("t1") == template

    def test_save_load(self, temp_registry_path):
        registry = PromptRegistry(temp_registry_path)
        template = PromptTemplate(
            id="t1", version=1, category=PromptCategory.HYPOTHESIS,
            description="d", template="t", variables=[]
        )
        registry.register(template)
        
        registry2 = PromptRegistry(temp_registry_path)
        assert "t1:v1" in registry2.templates
        assert registry2.get_latest("t1").id == "t1"

    def test_template_stats(self, temp_registry_path):
        registry = PromptRegistry(temp_registry_path)
        outcome = PromptOutcome(
            template_id="t1", template_version=1, provider="p1",
            prompt_text="p", response_text="r", success=True,
            metric_before=1.0, metric_after=2.0, iterations_used=1,
            tokens_estimate=10
        )
        registry.record_outcome(outcome)
        
        stats = registry.get_template_stats("t1")
        assert stats["count"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["avg_improvement"] == 1.0

class TestContextProvider:
    def test_set_get(self):
        provider = ContextProvider()
        provider.set("k1", "v1")
        assert provider.get("k1") == "v1"
        assert provider.get_context()["k1"] == "v1"

    def test_hooks(self):
        provider = ContextProvider()
        provider.register_hook(lambda: {"dynamic": "val"})
        assert provider.get_context()["dynamic"] == "val"

class TestUnifiedPromptEngine:
    @pytest.mark.asyncio
    async def test_execute_prompt(self, temp_registry_path):
        registry = PromptRegistry(temp_registry_path)
        template = PromptTemplate(
            id="t1", version=1, category=PromptCategory.HYPOTHESIS,
            description="d", template="Prompt: {val}", variables=["val"]
        )
        registry.register(template)
        
        bridge = MagicMock()
        bridge.process_prompt_async = AsyncMock(return_value=PromptResult(
            success=True, content="Response", provider="test-p",
            error=None, wait_time_ms=0
        ))
        bridge.get_status.return_value = MagicMock(providers={})
        
        engine = UnifiedPromptEngine(registry, bridge)
        
        # Test execute
        result = await engine.execute_prompt("t1", {"val": "hello"})
        
        assert result.success
        assert result.content == "Response"
        assert bridge.process_prompt_async.called
        
        # Verify outcome was recorded
        assert len(registry.outcomes) == 1
        assert registry.outcomes[0].template_id == "t1"

    def test_render_prompt_with_context(self, temp_registry_path):
        registry = PromptRegistry(temp_registry_path)
        template = PromptTemplate(
            id="t1", version=1, category=PromptCategory.HYPOTHESIS,
            description="d", template="User: {user}, Global: {glob}", 
            variables=["user", "glob"]
        )
        registry.register(template)
        
        engine = UnifiedPromptEngine(registry, MagicMock())
        engine.context.set("glob", "global-val")
        
        rendered = engine.render_prompt("t1", {"user": "alice"})
        assert rendered == "User: alice, Global: global-val"

    def test_update_metric(self, temp_registry_path):
        registry = PromptRegistry(temp_registry_path)
        outcome = PromptOutcome(
            template_id="t1", template_version=1, provider="p",
            prompt_text="p", response_text="r", success=True,
            metric_before=1.0, metric_after=None, iterations_used=1,
            tokens_estimate=10
        )
        registry.record_outcome(outcome)
        
        engine = UnifiedPromptEngine(registry, MagicMock())
        engine.update_metric(2.5, "t1")
        
        assert registry.outcomes[0].metric_after == 2.5

    def test_ascii_dashboard_update(self, temp_registry_path, tmp_path):
        registry = PromptRegistry(temp_registry_path)
        dashboard_path = tmp_path / "dashboard.ascii"
        engine = UnifiedPromptEngine(registry, MagicMock(), ascii_dashboard_path=dashboard_path)
        
        engine.write_ascii_dashboard(status="running", experiment={"hypothesis": "test"})
        
        assert (tmp_path / "dashboard_state.json").exists()
        assert dashboard_path.exists()
        assert "● running" in dashboard_path.read_text()

def test_create_default_engine(tmp_path):
    engine = create_default_engine(tmp_path)
    assert isinstance(engine, UnifiedPromptEngine)
    # Check if builtin templates are registered
    assert engine.registry.get_latest("hypothesis_generation") is not None
