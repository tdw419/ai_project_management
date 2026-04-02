"""
DEPRECATED: This module is from AIPM v1 and is NOT used by the v2 loop.
The v2 loop lives in aipm.loop.MultiProjectLoop.

This file is kept for reference only. Do not import from it.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional



class PromptCategory(str, Enum):
    """Categories of prompts"""
    CODE_GEN = "code_gen"
    ANALYSIS = "analysis"
    DEBUG = "debug"
    REFACTOR = "refactor"
    TEST = "test"
    DOC = "doc"
    DESIGN = "design"
    META = "meta"  # For improving the system itself


class PromptStatus(str, Enum):
    """Status of a prompt"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PromptTemplate:
    """A reusable prompt template"""
    id: str
    version: int
    category: PromptCategory
    description: str
    template: str
    variables: List[str] = field(default_factory=list)
    defaults: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def render(self, **kwargs) -> str:
        """Render the template with provided variables"""
        # Merge defaults with provided kwargs
        context = {**self.defaults, **kwargs}
        
        # Check for missing required variables
        missing = set(self.variables) - set(context.keys())
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        
        # Simple template substitution (Jinja2 can be added later)
        result = self.template
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value))
        
        return result


@dataclass
class Prompt:
    """A prompt in the system"""
    id: str
    text: str
    category: PromptCategory
    project_id: Optional[str] = None  # Added for v2 multi-project support
    priority: int = 5  # 1 = highest, 10 = lowest
    confidence: float = 0.5
    impact: float = 0.5
    status: PromptStatus = PromptStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    result: Optional[str] = None
    result_quality: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    template_id: Optional[str] = None
    parent_id: Optional[str] = None  # For follow-up prompts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "text": self.text,
            "category": self.category.value,
            "project_id": self.project_id,
            "priority": self.priority,
            "confidence": self.confidence,
            "impact": self.impact,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "result": self.result,
            "result_quality": self.result_quality,
            "metadata": self.metadata,
            "template_id": self.template_id,
            "parent_id": self.parent_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Prompt":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            text=data["text"],
            category=PromptCategory(data["category"]),
            project_id=data.get("project_id"),
            priority=data.get("priority", 5),
            confidence=data.get("confidence", 0.5),
            impact=data.get("impact", 0.5),
            status=PromptStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            result=data.get("result"),
            result_quality=data.get("result_quality"),
            metadata=data.get("metadata", {}),
            template_id=data.get("template_id"),
            parent_id=data.get("parent_id"),
        )


class LLMProvider:
    """Base class for LLM providers"""
    
    name: str = "base"
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from the prompt"""
        raise NotImplementedError
    
    async def is_available(self) -> bool:
        """Check if the provider is available"""
        return False


class LMStudioProvider(LLMProvider):
    """LM Studio local provider"""
    
    name = "lm_studio"
    
    def __init__(self, base_url: str = "http://localhost:1234"):
        self.base_url = base_url
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate via LM Studio API"""
        import httpx
        
        model = kwargs.get("model", "local-model")
        max_tokens = kwargs.get("max_tokens", 4096)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/completions",
                json={
                    "model": model,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": kwargs.get("temperature", 0.7),
                },
                timeout=kwargs.get("timeout", 120.0),
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["text"]
    
    async def is_available(self) -> bool:
        """Check if LM Studio is running"""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/v1/models", timeout=5.0)
                return response.status_code == 200
        except:
            return False


class MockProvider(LLMProvider):
    """Mock provider for testing"""
    
    name = "mock"
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Return a mock response"""
        return f"Mock response for: {prompt[:100]}..."
    
    async def is_available(self) -> bool:
        return True


class PromptRegistry:
    """Registry for prompt templates"""
    
    def __init__(self, path: Optional[Path] = None):
        self.templates: Dict[str, PromptTemplate] = {}
        self.path = path
        if path and path.exists():
            self.load(path)
    
    def register(self, template: PromptTemplate) -> None:
        """Register a template"""
        self.templates[template.id] = template
    
    def get(self, template_id: str) -> Optional[PromptTemplate]:
        """Get a template by ID"""
        return self.templates.get(template_id)
    
    def list_templates(self, category: Optional[PromptCategory] = None) -> List[PromptTemplate]:
        """List templates, optionally filtered by category"""
        templates = list(self.templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save templates to file"""
        path = path or self.path
        if not path:
            return
        
        data = {
            tid: {
                "id": t.id,
                "version": t.version,
                "category": t.category.value,
                "description": t.description,
                "template": t.template,
                "variables": t.variables,
                "defaults": t.defaults,
                "tags": t.tags,
            }
            for tid, t in self.templates.items()
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def load(self, path: Path) -> None:
        """Load templates from file"""
        if not path.exists():
            return
        
        with open(path) as f:
            data = json.load(f)
        
        for tid, tdata in data.items():
            self.register(PromptTemplate(
                id=tdata["id"],
                version=tdata["version"],
                category=PromptCategory(tdata["category"]),
                description=tdata["description"],
                template=tdata["template"],
                variables=tdata.get("variables", []),
                defaults=tdata.get("defaults", {}),
                tags=tdata.get("tags", []),
            ))


class PromptEngine:
    """
    The core prompt processing engine.
    
    Handles:
    - Template management
    - Multi-provider routing
    - Prompt execution
    """
    
    def __init__(self, registry_path: Optional[Path] = None):
        self.registry = PromptRegistry(registry_path)
        self.providers: Dict[str, LLMProvider] = {}
        self.default_provider = "mock"
        
        # Register default providers
        self.register_provider(MockProvider())
        self.register_provider(LMStudioProvider())
    
    def register_provider(self, provider: LLMProvider) -> None:
        """Register an LLM provider"""
        self.providers[provider.name] = provider
    
    def set_default_provider(self, name: str) -> None:
        """Set the default provider"""
        if name not in self.providers:
            raise ValueError(f"Unknown provider: {name}")
        self.default_provider = name
    
    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate a response using the specified provider"""
        provider_name = provider or self.default_provider
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        return await self.providers[provider_name].generate(prompt, **kwargs)
    
    def create_prompt_from_template(
        self,
        template_id: str,
        **variables
    ) -> str:
        """Create a prompt from a template"""
        template = self.registry.get(template_id)
        if not template:
            raise ValueError(f"Unknown template: {template_id}")
        
        return template.render(**variables)
    
    async def process_prompt(
        self,
        prompt: Prompt,
        provider: Optional[str] = None,
    ) -> str:
        """Process a prompt and return the result"""
        prompt.status = PromptStatus.PROCESSING
        prompt.updated_at = datetime.now()
        
        try:
            result = await self.generate(prompt.text, provider=provider)
            prompt.result = result
            prompt.status = PromptStatus.COMPLETED
            return result
        except Exception as e:
            prompt.status = PromptStatus.FAILED
            prompt.result = str(e)
            raise


class PromptSystem:
    """
    The complete prompt management system.
    
    Integrates:
    - PromptEngine for execution
    - PromptQueue for management
    - PromptPrioritizer for scoring
    - ResponseAnalyzer for quality assessment
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path.home() / ".aipm" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Import here to avoid circular imports
        from aipm.core.queue import PromptQueue
        # DEPRECATED: prioritizer and analyzer modules don't exist in v2.
        # PromptSystem is legacy v1 code -- do not use.
        self.engine = PromptEngine(self.data_dir / "templates.json")
        self.queue = PromptQueue(self.data_dir / "queue.db")
        self.prioritizer = None  # Was: PromptPrioritizer()
        self.analyzer = None     # Was: ResponseAnalyzer()
    
    def add_prompt(self, prompt: Prompt) -> None:
        """Add a prompt to the queue"""
        self.queue.add(prompt)
    
    def get_next_prompt(self) -> Optional[Prompt]:
        """Get the highest-priority prompt"""
        prompts = self.queue.get_pending()
        if not prompts:
            return None
        
        # Score and sort
        scored = [(p, self.prioritizer.score(p)) for p in prompts]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored[0][0]
    
    async def process_next(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Process the next prompt in the queue"""
        prompt = self.get_next_prompt()
        if not prompt:
            return {"status": "empty", "message": "No prompts in queue"}
        
        try:
            result = await self.engine.process_prompt(prompt, provider=provider)
            
            # Analyze the result
            analysis = self.analyzer.analyze(prompt)
            
            # Update prompt with quality
            prompt.result_quality = analysis.quality.value
            
            # Generate follow-ups if needed
            followups = []
            if analysis.needs_followup:
                followups = self.analyzer.generate_followups(prompt, analysis)
                for fp in followups:
                    self.add_prompt(fp)
            
            # Save changes
            self.queue.update(prompt)
            
            return {
                "status": "success",
                "prompt_id": prompt.id,
                "result": result,
                "quality": analysis.quality.value,
                "followups_generated": len(followups),
            }
        except Exception as e:
            return {
                "status": "error",
                "prompt_id": prompt.id,
                "error": str(e),
            }
    
    async def run_forever(self, interval: int = 60, provider: Optional[str] = None) -> None:
        """Run the processing loop forever"""
        while True:
            result = await self.process_next(provider=provider)
            print(f"[{datetime.now().isoformat()}] {result}")
            await asyncio.sleep(interval)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        return {
            "queue": self.queue.get_stats(),
            "providers": list(self.engine.providers.keys()),
            "templates": len(self.engine.registry.templates),
        }
