"""Tests for AIPM core components"""

import pytest
from datetime import datetime, timedelta

from aipm.core.engine import (
    Prompt,
    PromptTemplate,
    PromptCategory,
    PromptStatus,
    PromptEngine,
    PromptRegistry,
)
from aipm.core.prioritizer import PromptPrioritizer
from aipm.core.analyzer import ResponseAnalyzer, QualityLevel


class TestPrompt:
    """Tests for Prompt class"""
    
    def test_prompt_creation(self):
        """Test creating a prompt"""
        prompt = Prompt(
            id="test_1",
            text="Write a function to sort a list",
            category=PromptCategory.CODE_GEN,
            priority=1,
        )
        
        assert prompt.id == "test_1"
        assert prompt.status == PromptStatus.PENDING
        assert prompt.priority == 1
    
    def test_prompt_serialization(self):
        """Test prompt serialization"""
        prompt = Prompt(
            id="test_2",
            text="Debug the error",
            category=PromptCategory.DEBUG,
            priority=2,
            confidence=0.8,
        )
        
        data = prompt.to_dict()
        assert data["id"] == "test_2"
        assert data["category"] == "debug"
        
        restored = Prompt.from_dict(data)
        assert restored.id == prompt.id
        assert restored.category == prompt.category


class TestPromptTemplate:
    """Tests for PromptTemplate class"""
    
    def test_template_rendering(self):
        """Test template rendering"""
        template = PromptTemplate(
            id="test_template",
            version=1,
            category=PromptCategory.CODE_GEN,
            description="Test template",
            template="Write a {language} function to {task}",
            variables=["language", "task"],
        )
        
        result = template.render(language="Python", task="sort a list")
        assert result == "Write a Python function to sort a list"
    
    def test_template_with_defaults(self):
        """Test template with defaults"""
        template = PromptTemplate(
            id="test_template_2",
            version=1,
            category=PromptCategory.CODE_GEN,
            description="Test template",
            template="Write code in {language}",
            variables=["language"],
            defaults={"language": "Python"},
        )
        
        result = template.render()
        assert result == "Write code in Python"


class TestPromptPrioritizer:
    """Tests for PromptPrioritizer class"""
    
    def test_priority_scoring(self):
        """Test priority scoring"""
        prioritizer = PromptPrioritizer()
        
        # High priority prompt
        high = Prompt(
            id="high",
            text="Urgent task",
            category=PromptCategory.DEBUG,
            priority=1,  # Most urgent
            confidence=0.9,
            impact=0.8,
        )
        
        # Low priority prompt
        low = Prompt(
            id="low",
            text="Low priority task",
            category=PromptCategory.DOC,
            priority=10,  # Least urgent
            confidence=0.5,
            impact=0.3,
        )
        
        high_score = prioritizer.score(high)
        low_score = prioritizer.score(low)
        
        assert high_score > low_score
    
    def test_freshness_bonus(self):
        """Test freshness bonus"""
        prioritizer = PromptPrioritizer()
        
        fresh = Prompt(
            id="fresh",
            text="Fresh prompt",
            category=PromptCategory.CODE_GEN,
            created_at=datetime.now(),
        )
        
        stale = Prompt(
            id="stale",
            text="Stale prompt",
            category=PromptCategory.CODE_GEN,
            created_at=datetime.now() - timedelta(hours=48),
        )
        
        fresh_score = prioritizer.score(fresh)
        stale_score = prioritizer.score(stale)
        
        # Fresh should get bonus, stale should get penalty
        assert fresh_score > stale_score
    
    def test_ranking(self):
        """Test prompt ranking"""
        prioritizer = PromptPrioritizer()
        
        prompts = [
            Prompt(id="p1", text="Low", category=PromptCategory.CODE_GEN, priority=10),
            Prompt(id="p2", text="High", category=PromptCategory.CODE_GEN, priority=1),
            Prompt(id="p3", text="Medium", category=PromptCategory.CODE_GEN, priority=5),
        ]
        
        ranked = prioritizer.rank(prompts)
        
        assert ranked[0][0].id == "p2"  # High priority first
        assert ranked[-1][0].id == "p1"  # Low priority last


class TestResponseAnalyzer:
    """Tests for ResponseAnalyzer class"""
    
    def test_complete_detection(self):
        """Test detecting complete responses"""
        analyzer = ResponseAnalyzer()
        
        prompt = Prompt(
            id="test",
            text="Write a function",
            category=PromptCategory.CODE_GEN,
            result="I have successfully implemented the function. The code is complete and working.",
        )
        
        analysis = analyzer.analyze(prompt)
        
        assert analysis.quality == QualityLevel.COMPLETE
        assert "complete" in [i.lower() for i in analysis.success_indicators]
    
    def test_failure_detection(self):
        """Test detecting failed responses"""
        analyzer = ResponseAnalyzer()
        
        prompt = Prompt(
            id="test",
            text="Fix the bug",
            category=PromptCategory.DEBUG,
            result="Error: Failed to connect to database. The operation timed out.",
        )
        
        analysis = analyzer.analyze(prompt)
        
        assert analysis.quality == QualityLevel.FAILED
        assert analysis.needs_followup
    
    def test_incomplete_detection(self):
        """Test detecting incomplete responses"""
        analyzer = ResponseAnalyzer()
        
        prompt = Prompt(
            id="test",
            text="Implement feature",
            category=PromptCategory.CODE_GEN,
            result="I've started implementing the feature. TODO: Add tests. FIXME: Handle edge cases.",
        )
        
        analysis = analyzer.analyze(prompt)
        
        assert analysis.quality in [QualityLevel.PARTIAL, QualityLevel.NEEDS_REVIEW]
        assert analysis.needs_followup
    
    def test_followup_generation(self):
        """Test generating follow-up prompts"""
        analyzer = ResponseAnalyzer()
        
        prompt = Prompt(
            id="test",
            text="Write code",
            category=PromptCategory.CODE_GEN,
            result="Error: Could not compile.",
        )
        
        analysis = analyzer.analyze(prompt)
        followups = analyzer.generate_followups(prompt, analysis)
        
        assert len(followups) > 0
        assert followups[0].parent_id == prompt.id


class TestPromptEngine:
    """Tests for PromptEngine class"""
    
    @pytest.mark.asyncio
    async def test_mock_provider(self):
        """Test mock provider"""
        engine = PromptEngine()
        engine.set_default_provider("mock")
        
        result = await engine.generate("Test prompt")
        assert "Mock response" in result
    
    def test_template_registration(self):
        """Test template registration"""
        engine = PromptEngine()
        
        template = PromptTemplate(
            id="test",
            version=1,
            category=PromptCategory.CODE_GEN,
            description="Test",
            template="Hello {name}",
            variables=["name"],
        )
        
        engine.registry.register(template)
        
        retrieved = engine.registry.get("test")
        assert retrieved is not None
        assert retrieved.template == "Hello {name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
