"""
Unified Prompt Engine

Single entry point for all prompting with:
- Template versioning and library
- Multi-provider routing via queue bridge
- Context injection
- Success tracking and analytics
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
import json
import re

from .queue_bridge import PromptQueueBridge, PromptResult


class PromptCategory(Enum):
    HYPOTHESIS = "hypothesis"
    REFLECTION = "reflection"
    CODE_GEN = "code_gen"
    ANALYSIS = "analysis"
    META = "meta"


@dataclass
class PromptTemplate:
    """Versioned, parameterized prompt template."""
    id: str
    version: int
    category: PromptCategory
    description: str
    template: str
    variables: List[str]
    defaults: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self, **kwargs) -> List[str]:
        """Check for missing required variables."""
        missing = []
        for var in self.variables:
            if var not in kwargs and var not in self.defaults:
                missing.append(var)
        return missing
    
    def render(self, **kwargs) -> str:
        """Render template with variables."""
        # Merge defaults with provided kwargs
        full_vars = {**self.defaults, **kwargs}
        
        # Validate
        missing = self.validate(**full_vars)
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        
        # Simple string formatting (supports {variable} syntax)
        result = self.template
        for key, value in full_vars.items():
            result = result.replace(f"{{{key}}}", str(value))
        
        return result
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "category": self.category.value,
            "description": self.description,
            "template": self.template,
            "variables": self.variables,
            "defaults": self.defaults,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PromptTemplate":
        return cls(
            id=data["id"],
            version=data["version"],
            category=PromptCategory(data.get("category", "analysis")),
            description=data.get("description", ""),
            template=data["template"],
            variables=data.get("variables", []),
            defaults=data.get("defaults", {}),
            metadata=data.get("metadata", {})
        )


@dataclass
class PromptOutcome:
    """Record of a prompt execution and its outcome."""
    template_id: str
    template_version: int
    provider: str
    prompt_text: str
    response_text: str
    success: bool
    metric_before: Optional[float]
    metric_after: Optional[float]
    iterations_used: int
    tokens_estimate: int
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    
    @property
    def metric_improvement(self) -> Optional[float]:
        if self.metric_before is not None and self.metric_after is not None:
            return self.metric_after - self.metric_before
        return None
    
    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "template_version": self.template_version,
            "provider": self.provider,
            "success": self.success,
            "metric_improvement": self.metric_improvement,
            "iterations_used": self.iterations_used,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error
        }


class PromptRegistry:
    """
    Central registry for prompt templates.
    
    Supports:
    - Version management
    - Category filtering
    - Success rate tracking
    - Import/export
    """
    
    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path
        self.templates: Dict[str, PromptTemplate] = {}
        self.outcomes: List[PromptOutcome] = []
        
        if registry_path and registry_path.exists():
            self._load()
    
    def _load(self):
        """Load templates from registry file."""
        if not self.registry_path:
            return
        
        try:
            with open(self.registry_path) as f:
                data = json.load(f)
            
            for t_data in data.get("templates", []):
                template = PromptTemplate.from_dict(t_data)
                key = f"{template.id}:v{template.version}"
                self.templates[key] = template
            
            for o_data in data.get("outcomes", []):
                self.outcomes.append(PromptOutcome(
                    template_id=o_data["template_id"],
                    template_version=o_data["template_version"],
                    provider=o_data["provider"],
                    prompt_text=o_data.get("prompt_text", ""),
                    response_text=o_data.get("response_text", ""),
                    success=o_data["success"],
                    metric_before=o_data.get("metric_before"),
                    metric_after=o_data.get("metric_after"),
                    iterations_used=o_data.get("iterations_used", 0),
                    tokens_estimate=o_data.get("tokens_estimate", 0),
                    error=o_data.get("error")
                ))
        except Exception as e:
            print(f"Warning: Failed to load registry: {e}")
    
    def _save(self):
        """Save templates to registry file."""
        if not self.registry_path:
            return
        
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "templates": [t.to_dict() for t in self.templates.values()],
            "outcomes": [o.to_dict() for o in self.outcomes[-1000:]]  # Keep last 1000
        }
        
        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def register(self, template: PromptTemplate) -> str:
        """Register a template, returns key."""
        key = f"{template.id}:v{template.version}"
        self.templates[key] = template
        self._save()
        return key
    
    def get(self, key: str) -> Optional[PromptTemplate]:
        """Get template by exact key."""
        return self.templates.get(key)
    
    def get_latest(self, template_id: str) -> Optional[PromptTemplate]:
        """Get latest version of a template by ID."""
        versions = [
            t for k, t in self.templates.items()
            if t.id == template_id
        ]
        if not versions:
            return None
        return max(versions, key=lambda t: t.version)
    
    def get_by_category(self, category: PromptCategory) -> List[PromptTemplate]:
        """Get all templates in a category (latest versions only)."""
        by_id: Dict[str, PromptTemplate] = {}
        for t in self.templates.values():
            if t.category == category:
                if t.id not in by_id or t.version > by_id[t.id].version:
                    by_id[t.id] = t
        return list(by_id.values())
    
    def record_outcome(self, outcome: PromptOutcome):
        """Record a prompt outcome for analytics."""
        self.outcomes.append(outcome)
        self._save()
    
    def get_template_stats(self, template_id: str) -> Dict[str, Any]:
        """Get statistics for a template."""
        template_outcomes = [
            o for o in self.outcomes
            if o.template_id == template_id
        ]
        
        if not template_outcomes:
            return {"count": 0}
        
        successes = [o for o in template_outcomes if o.success]
        improvements = [o.metric_improvement for o in successes if o.metric_improvement is not None]
        
        return {
            "count": len(template_outcomes),
            "success_count": len(successes),
            "success_rate": len(successes) / len(template_outcomes),
            "avg_improvement": sum(improvements) / len(improvements) if improvements else None,
            "avg_iterations": sum(o.iterations_used for o in template_outcomes) / len(template_outcomes),
            "by_provider": self._group_outcomes_by_provider(template_outcomes)
        }
    
    def _group_outcomes_by_provider(self, outcomes: List[PromptOutcome]) -> Dict[str, Dict]:
        """Group outcomes by provider."""
        by_provider: Dict[str, List[PromptOutcome]] = {}
        for o in outcomes:
            if o.provider not in by_provider:
                by_provider[o.provider] = []
            by_provider[o.provider].append(o)
        
        return {
            provider: {
                "count": len(outs),
                "success_rate": sum(1 for o in outs if o.success) / len(outs)
            }
            for provider, outs in by_provider.items()
        }
    
    def recommend_template(self, category: PromptCategory) -> Optional[str]:
        """Recommend best-performing template in category."""
        templates = self.get_by_category(category)
        
        if not templates:
            return None
        
        # Score by success rate
        scored = []
        for t in templates:
            stats = self.get_template_stats(t.id)
            if stats["count"] > 0:
                score = stats["success_rate"]
                scored.append((t.id, score))
        
        if not scored:
            return templates[0].id  # No data, return first
        
        return max(scored, key=lambda x: x[1])[0]


class ContextProvider:
    """Provides context for prompt rendering."""
    
    def __init__(self):
        self._context: Dict[str, Any] = {}
        self._hooks: List[Callable[[], Dict[str, Any]]] = []
    
    def set(self, key: str, value: Any):
        """Set a context value."""
        self._context[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self._context.get(key, default)
    
    def register_hook(self, hook: Callable[[], Dict[str, Any]]):
        """Register a function to be called for dynamic context."""
        self._hooks.append(hook)
    
    def get_context(self) -> Dict[str, Any]:
        """Get all context including dynamic hooks."""
        context = dict(self._context)
        for hook in self._hooks:
            try:
                context.update(hook())
            except Exception as e:
                print(f"Warning: Context hook failed: {e}")
        return context


class UnifiedPromptEngine:
    """
    Single entry point for all prompting in Ouroboros.
    
    Features:
    - Template-based prompts with versioning
    - Multi-provider routing via queue bridge
    - Context injection
    - Success tracking and analytics
    - Automatic template recommendations
    - ASCII World integration for visual feedback
    """
    
    def __init__(self,
                 registry: PromptRegistry,
                 queue_bridge: PromptQueueBridge,
                 context_provider: Optional[ContextProvider] = None,
                 ascii_dashboard_path: Optional[Path] = None):
        self.registry = registry
        self.bridge = queue_bridge
        self.context = context_provider or ContextProvider()
        self._current_metric: Optional[float] = None
        
        # ASCII World integration
        self.ascii_dashboard_path = ascii_dashboard_path
        self._ascii_state: Dict[str, Any] = {
            "status": "idle",
            "iteration": 0,
            "max_iterations": 15,
            "providers": {},
            "experiment": None,
            "tree": {"nodes": [], "best": None, "current": None},
            "rules": [],
            "templates": {},
            "total_prompts": 0
        }
    
    def set_current_metric(self, metric: float):
        """Set current metric for outcome tracking."""
        self._current_metric = metric
    
    def render_prompt(self,
                      template_id: str,
                      variables: Optional[Dict[str, Any]] = None,
                      version: Optional[int] = None) -> str:
        """
        Render a prompt from template.
        
        Args:
            template_id: Template ID (without version)
            variables: Variables to inject
            version: Specific version (None = latest)
        
        Returns:
            Rendered prompt text
        """
        if version:
            template = self.registry.get(f"{template_id}:v{version}")
        else:
            template = self.registry.get_latest(template_id)
        
        if not template:
            raise ValueError(f"Template not found: {template_id}")
        
        # Merge context with provided variables
        full_vars = {**self.context.get_context(), **(variables or {})}
        
        return template.render(**full_vars)
    
    async def execute_prompt(self,
                             template_id: str,
                             variables: Optional[Dict[str, Any]] = None,
                             priority: int = 5,
                             preferred_provider: Optional[str] = None,
                             track_outcome: bool = True) -> PromptResult:
        """
        Render and execute a prompt through the queue.
        
        Args:
            template_id: Template ID
            variables: Variables to inject
            priority: Queue priority (1-10, lower = higher)
            preferred_provider: Preferred provider
            track_outcome: Record outcome for analytics
        
        Returns:
            PromptResult from queue
        """
        # Get template
        template = self.registry.get_latest(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")
        
        # Render
        prompt_text = self.render_prompt(template_id, variables)
        
        # Execute via queue
        result = await self.bridge.process_prompt_async(
            prompt_text,
            priority=priority,
            preferred_provider=preferred_provider
        )
        
        # Track outcome
        if track_outcome:
            outcome = PromptOutcome(
                template_id=template.id,
                template_version=template.version,
                provider=result.provider or "unknown",
                prompt_text=prompt_text,
                response_text=result.content or "",
                success=result.success,
                metric_before=self._current_metric,
                metric_after=None,  # Updated later
                iterations_used=1,
                tokens_estimate=len(prompt_text.split()) * 4,  # Rough estimate
                error=result.error
            )
            self.registry.record_outcome(outcome)
        
        # Update ASCII dashboard
        self._update_ascii_after_prompt(template_id, variables, result)
        
        return result
    
    def _update_ascii_after_prompt(self, template_id: str, variables: Dict, result: PromptResult):
        """Update ASCII dashboard after prompt execution."""
        try:
            # Get provider status
            queue_status = self.bridge.get_status(use_cache=True)
            providers = {}
            for name, prov in queue_status.providers.items():
                providers[name] = {
                    "available": prov.available,
                    "used": prov.used,
                    "limit": prov.limit,
                    "rate_limited": prov.rate_limited
                }
            
            # Get learned rules from semantic analyzer if available
            rules = []
            if hasattr(self, 'semantic_analyzer') and self.semantic_analyzer:
                for rule in self.semantic_analyzer.get_rules()[:5]:
                    rules.append({
                        "text": rule,
                        "successRate": 0.7  # Default confidence
                    })
            
            # Update dashboard
            self.write_ascii_dashboard(
                status="running" if result.success else "error",
                experiment={
                    "hypothesis": variables.get("goal", "")[:50] if variables else "",
                    "target": "unknown",
                    "metric": variables.get("success_criteria", "") if variables else "",
                    "budget": "5m"
                },
                providers=providers,
                rules=rules
            )
        except Exception as e:
            # Don't fail the prompt if dashboard update fails
            print(f"Warning: Failed to update ASCII dashboard: {e}")
    
    def update_metric(self, metric_after: float, template_id: Optional[str] = None):
        """Update the last outcome with the new metric."""
        if self.registry.outcomes and template_id:
            # Find last outcome for this template
            for outcome in reversed(self.registry.outcomes):
                if outcome.template_id == template_id and outcome.metric_after is None:
                    outcome.metric_after = metric_after
                    self.registry._save()
                    break
    
    def get_best_template(self, category: PromptCategory) -> str:
        """Get recommended template for a category."""
        recommended = self.registry.recommend_template(category)
        if recommended:
            return recommended
        
        # Fallback to first available
        templates = self.registry.get_by_category(category)
        if templates:
            return templates[0].id
        
        raise ValueError(f"No templates found for category: {category}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall engine statistics."""
        all_outcomes = self.registry.outcomes
        
        if not all_outcomes:
            return {"total_prompts": 0}
        
        return {
            "total_prompts": len(all_outcomes),
            "success_rate": sum(1 for o in all_outcomes if o.success) / len(all_outcomes),
            "templates_used": len(set(o.template_id for o in all_outcomes)),
            "providers_used": list(set(o.provider for o in all_outcomes)),
            "recent_success_rate": sum(1 for o in all_outcomes[-50:] if o.success) / min(50, len(all_outcomes))
        }
    
    # === ASCII World Integration ===
    
    def update_ascii_state(self, **updates):
        """
        Update the ASCII dashboard state.
        
        Call this to update the visual dashboard that humans see.
        Changes are written to dashboard_state.json for sync-server.js to broadcast.
        """
        self._ascii_state.update(updates)
        self._ascii_state["total_prompts"] = len(self.registry.outcomes)
        self._write_ascii_state()
    
    def _write_ascii_state(self):
        """Write state to JSON file for sync-server to read."""
        if not self.ascii_dashboard_path:
            return
        
        state_file = self.ascii_dashboard_path.parent / "dashboard_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(state_file, "w") as f:
            json.dump(self._ascii_state, f, indent=2)
    
    def write_ascii_dashboard(self, 
                               status: Optional[str] = None,
                               experiment: Optional[Dict] = None,
                               providers: Optional[Dict] = None,
                               rules: Optional[List] = None,
                               tree: Optional[Dict] = None):
        """
        Write current state to ASCII dashboard substrate.
        
        This is the main integration point - call after each prompt execution
        to update the visual dashboard.
        
        Args:
            status: Loop status (idle, running, paused, error, stopped)
            experiment: Current experiment spec {hypothesis, target, metric, budget}
            providers: Provider status dict from bridge.get_status()
            rules: Learned rules list from semantic analyzer
            tree: Experiment tree state
        """
        if status:
            self._ascii_state["status"] = status
        
        if experiment:
            self._ascii_state["experiment"] = experiment
        
        if providers:
            self._ascii_state["providers"] = providers
        
        if rules:
            self._ascii_state["rules"] = rules
        
        if tree:
            self._ascii_state["tree"] = tree
        
        # Update iteration count
        self._ascii_state["iteration"] = len(self.registry.outcomes)
        
        self._write_ascii_state()
    
    def generate_ascii_file(self) -> str:
        """Generate the full dashboard.ascii file content."""
        s = self._ascii_state
        
        status_symbol = {
            "running": "●",
            "paused": "◐", 
            "idle": "○",
            "stopped": "○",
            "error": "◉"
        }.get(s.get("status", "idle"), "○")
        
        # Provider bars
        provider_lines = []
        for name, p in s.get("providers", {}).items():
            if isinstance(p, dict):
                symbol = "●" if p.get("available") else "○"
                used = p.get("used", 0)
                limit = p.get("limit", 1000)
                bar_len = 10
                filled = int((used / limit) * bar_len) if limit > 0 else 0
                bar = "█".repeat(filled) + "░".repeat(bar_len - filled)
                provider_lines.append(f"│  {symbol} {name:<8} [{bar}] {used}/{limit}")
        
        # Experiment section
        exp = s.get("experiment", {}) or {}
        exp_lines = f"""│  H: {exp.get('hypothesis', 'N/A'):<34}│
│  T: {exp.get('target', 'N/A'):<34}│
│  M: {exp.get('metric', 'N/A'):<34}│
│  B: {exp.get('budget', '5m'):<34}│"""
        
        # Rules section
        rules_lines = []
        for rule in s.get("rules", [])[:5]:
            icon = "✓" if rule.get("successRate", 0) >= 0.7 else ("◐" if rule.get("successRate", 0) >= 0.4 else "✗")
            rules_lines.append(f"│  {icon} {rule.get('text', ''):<30)} {int(rule.get('successRate', 0) * 100)}% │")
        
        content = f"""# Ouroboros ASCII Dashboard

ver:{hashlib.md5(content.encode()).hexdigest()[:8]}

┌──────────────────────────────────────────────────────────────────────────┐
│  OUROBOROS PROMPT ENGINE - Live Dashboard                                │
├──────────────────────────────────────────────────────────────────────────┤
│  Status: {status_symbol} {s.get('status', 'idle'):<8} Iteration: {s.get('iteration', 0):<2}/{s.get('max_iterations', 15)}  Convergence: {min(100, s.get('iteration', 0) * 100 // s.get('max_iterations', 1))}%   │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────┐  ┌─────────────────────────────┐
│  PROVIDER QUEUE                             │  │  ACTIVE EXPERIMENT          │
├─────────────────────────────────────────┤  ├─────────────────────────────┤
{chr(10).join(provider_lines)}
│                                         │  │{exp_lines}
│  Next available: ...                    │  │                             │
└─────────────────────────────────────────┘  └─────────────────────────────┘

┌─────────────────────────────────────────┐  ┌─────────────────────────────┐
│  LEARNED RULES                              │  │  TEMPLATE STATS             │
├─────────────────────────────────────────┤  ├─────────────────────────────┤
{chr(10).join(rules_lines) if rules_lines else "│  No rules learned yet        │"}
│                                         │  │                             │
│  [G] Generate new rules                 │  │  Total prompts: {s.get('total_prompts', 0):<11}        │
└─────────────────────────────────────────┘  └─────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  ACTIONS                                                                  │
├──────────────────────────────────────────────────────────────────────────┤
│  [S] Start Loop    [P] Pause    [R] Rollback    [E] Export    [X] Exit   │
└──────────────────────────────────────────────────────────────────────────┘
"""
        return content
    
    # === ASCII World Integration ===
    
    def update_ascii_state(self, **updates):
        """
        Update the ASCII dashboard state.
        
        Call this to update the visual dashboard that humans see.
        Changes are written to dashboard_state.json for sync-server.js to broadcast.
        """
        self._ascii_state.update(updates)
        self._ascii_state["total_prompts"] = len(self.registry.outcomes)
        self._write_ascii_state()
    
    def _write_ascii_state(self):
        """Write state to JSON file for sync-server to read."""
        if not self.ascii_dashboard_path:
            return
        
        import json
        state_file = self.ascii_dashboard_path.parent / "dashboard_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(state_file, "w") as f:
            json.dump(self._ascii_state, f, indent=2)
    
    def write_ascii_dashboard(self, 
                               status: Optional[str] = None,
                               experiment: Optional[Dict] = None,
                               providers: Optional[Dict] = None,
                               rules: Optional[List] = None,
                               tree: Optional[Dict] = None):
        """
        Write current state to ASCII dashboard substrate.
        
        This is the main integration point - call after each prompt execution
        to update the visual dashboard.
        
        Args:
            status: Loop status (idle, running, paused, error, stopped)
            experiment: Current experiment spec {hypothesis, target, metric, budget}
            providers: Provider status dict
            rules: Learned rules list
            tree: Experiment tree state
        """
        if status:
            self._ascii_state["status"] = status
        
        if experiment:
            self._ascii_state["experiment"] = experiment
        
        if providers:
            self._ascii_state["providers"] = providers
        
        if rules:
            self._ascii_state["rules"] = rules
        
        if tree:
            self._ascii_state["tree"] = tree
        
        # Update iteration count
        if self.registry.outcomes:
            self._ascii_state["iteration"] = len([
                o for o in self.registry.outcomes 
                if o.success
            ])
        
        self._write_ascii_state()
        
        # Also generate and write ASCII file
        self._generate_ascii_file()
    
    def _generate_ascii_file(self):
        """Generate the dashboard.ascii file from current state."""
        if not self.ascii_dashboard_path:
            return
        
        import hashlib
        state = self._ascii_state
        
        # Generate ASCII content
        status_symbol = {
            "running": "●",
            "paused": "◐", 
            "idle": "○",
            "stopped": "○",
            "error": "◉"
        }.get(state.get("status", "idle"), "○")
        
        # Provider section
        provider_lines = []
        for name, p in state.get("providers", {}).items():
            if isinstance(p, dict):
                symbol = "●" if p.get("available") else "○"
                used = p.get("used", 0)
                limit = p.get("limit", 1000)
                bar_len = 10
                filled = int((used / limit) * bar_len) if limit > 0 else 0
                bar = "█" * filled + "░" * (bar_len - filled)
                provider_lines.append(f"│  {symbol} {name:<8} [{bar}] {used}/{limit}")
        
        # Experiment section
        exp = state.get("experiment") or {}
        exp_lines = []
        if exp.get("hypothesis"):
            exp_lines.append(f"│  H: {exp.get('hypothesis', '')[:34]}")
            exp_lines.append(f"│  T: {exp.get('target', '')[:34]}")
            exp_lines.append(f"│  M: {exp.get('metric', '')[:34]}")
            exp_lines.append(f"│  B: {exp.get('budget', '5m')[:34]}")
        
        # Rules section
        rule_lines = []
        for rule in state.get("rules", [])[:5]:
            if isinstance(rule, dict):
                rate = rule.get("successRate", 0)
                icon = "✓" if rate >= 0.7 else ("◐" if rate >= 0.4 else "✗")
                text = rule.get("text", "")[:30]
                rule_lines.append(f"│  {icon} {text:<30} {int(rate * 100)}%")
        
        # Template stats
        template_lines = []
        stats = self.get_stats()
        for t in self.registry.get_by_category(PromptCategory.HYPOTHESIS)[:3]:
            t_stats = self.registry.get_template_stats(t.id)
            if t_stats.get("count", 0) > 0:
                rate = int(t_stats.get("success_rate", 0) * 100)
                template_lines.append(f"│  {t.id}: {rate}%")
        
        # Build ASCII content
        iteration = state.get("iteration", 0)
        max_iter = state.get("max_iterations", 15)
        convergence = min(100, int((iteration / max_iter) * 100)) if max_iter > 0 else 0
        
        ascii_content = f"""# Ouroboros ASCII Dashboard

ver:pending

┌──────────────────────────────────────────────────────────────────────────┐
│  OUROBOROS PROMPT ENGINE - Live Dashboard                                │
├──────────────────────────────────────────────────────────────────────────┤
│  Status: {status_symbol} {state.get('status', 'idle'):<10} Iteration: {iteration:<2}/{max_iter}    Convergence: {convergence}%   │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────┐  ┌─────────────────────────────┐
│  PROVIDER QUEUE                         │  │  ACTIVE EXPERIMENT          │
├─────────────────────────────────────────┤  ├─────────────────────────────┤
{chr(10).join(provider_lines) if provider_lines else '│  No provider data                        │'}
│                                         │  │{chr(10).join(exp_lines) if exp_lines else '│  No active experiment                   │'}
└─────────────────────────────────────────┘  └─────────────────────────────┘

┌─────────────────────────────────────────┐  ┌─────────────────────────────┐
│  LEARNED RULES                          │  │  TEMPLATE STATS             │
├─────────────────────────────────────────┤  ├─────────────────────────────┤
{chr(10).join(rule_lines) if rule_lines else '│  No rules learned yet                   │'}
│                                         │  │{chr(10).join(template_lines) if template_lines else '│  No template data                        │'}
│  [G] Generate new rules                 │  │  Total prompts: {stats.get('total_prompts', 0)}        │
└─────────────────────────────────────────┘  └─────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  ACTIONS                                                                  │
├──────────────────────────────────────────────────────────────────────────┤
│  [S] Start Loop    [P] Pause    [R] Rollback    [E] Export    [X] Exit   │
└──────────────────────────────────────────────────────────────────────────┘
"""
        
        # Compute hash
        content_hash = hashlib.md5(ascii_content.encode()).hexdigest()[:8]
        ascii_content = ascii_content.replace("ver:pending", f"ver:{content_hash}")
        
        # Write file
        self.ascii_dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ascii_dashboard_path, "w") as f:
            f.write(ascii_content)
        
        return content_hash


# === Built-in Templates ===

BUILTIN_TEMPLATES = [
    PromptTemplate(
        id="hypothesis_generation",
        version=1,
        category=PromptCategory.HYPOTHESIS,
        description="Generate next hypothesis from experiment tree",
        template="""You are an autonomous research strategist in a recursive self-improvement loop.

## Current State
- **Goal**: {goal}
- **Success Criteria**: {success_criteria}
- **Current Iteration**: {iteration}

## Experiment History
{tree_ascii}

## Recent Results
{recent_results}

## Codebase Context
{codebase_context}

## Your Task
Based on the experiment tree and results, decide:
1. **REFINE**: Continue improving current best branch
2. **PIVOT**: Backtrack to a previous node and try different approach  
3. **HALT**: Goal achieved or impossible

Output in ASCII spec format:
┌───────────────────────────────────────┐
│ DECISION: <REFINE | PIVOT node_id>    │
├───────────────────────────────────────┤
│ H: <hypothesis - what to test>        │
│ T: <target - file(s) to modify>       │
│ M: <metric - success criteria>        │
│ B: <budget - time limit>              │
└───────────────────────────────────────┘

After the ASCII block, provide the full content of the target file in a markdown code block.""",
        variables=["goal", "success_criteria", "iteration", "tree_ascii", "recent_results", "codebase_context"],
        defaults={"iteration": "1"},
        metadata={"success_rate": 0.78, "tags": ["research", "hypothesis"]}
    ),
    
    PromptTemplate(
        id="reflection",
        version=1,
        category=PromptCategory.REFLECTION,
        description="Reflect on recent work and generate insights",
        template="""You are in an Ouroboros Recursive Self-Improvement Loop.

## Current State
- Iteration: {iteration}
- Phase: {milestone}
- Focus: {current_focus}

## Learned Rules
{learned_rules}

## Recent Messages
{recent_messages}

## Your Task
Reflect on the recent conversation and:
1. Identify what worked well
2. Identify what didn't work
3. Generate insights for future iterations

Format your response as:
FOCUS: [Short description of next focus]
INSIGHT: [Key insight from this iteration]
PROMPT: [The actual prompt you want to execute next]""",
        variables=["iteration", "milestone", "current_focus", "learned_rules", "recent_messages"],
        defaults={"iteration": "1", "milestone": "Unknown", "current_focus": "Initializing", "learned_rules": "None yet"},
        metadata={"tags": ["reflection", "meta"]}
    ),
    
    PromptTemplate(
        id="code_generation",
        version=1,
        category=PromptCategory.CODE_GEN,
        description="Generate code based on specification",
        template="""Generate code for the following specification.

## Task
{task_description}

## Constraints
{constraints}

## Context
{code_context}

## Requirements
1. Follow the existing code style
2. Include error handling
3. Add docstrings for functions
4. Ensure the code is testable

Output the complete implementation in a single code block.""",
        variables=["task_description", "constraints", "code_context"],
        defaults={"constraints": "None specified", "code_context": "No additional context"},
        metadata={"tags": ["code", "generation"]}
    ),
    
    PromptTemplate(
        id="metric_analysis",
        version=1,
        category=PromptCategory.ANALYSIS,
        description="Analyze metrics and suggest improvements",
        template="""Analyze the following metrics and suggest improvements.

## Current Metrics
{current_metrics}

## Historical Metrics
{historical_metrics}

## Goal
{goal}

## Your Task
1. Identify trends in the metrics
2. Find correlations between changes and metric changes
3. Suggest specific improvements to try
4. Estimate impact of each suggestion

Format your response as:
TREND: [Identified trend]
CORRELATION: [Correlation found]
SUGGESTIONS:
- [Suggestion 1] (estimated impact: X%)
- [Suggestion 2] (estimated impact: Y%)""",
        variables=["current_metrics", "historical_metrics", "goal"],
        defaults={"historical_metrics": "No historical data"},
        metadata={"tags": ["analysis", "metrics"]}
    ),
    
    PromptTemplate(
        id="meta_prompt_update",
        version=1,
        category=PromptCategory.META,
        description="Update system prompts based on learned patterns",
        template="""Based on recent patterns, suggest updates to the system prompt.

## Current System Prompt
{current_prompt}

## Detected Patterns
{patterns}

## Recent Outcomes
{outcomes}

## Your Task
1. Analyze which patterns are beneficial vs harmful
2. Suggest specific rules to add to the system prompt
3. Suggest rules to remove or modify
4. Explain the reasoning for each change

Format each new rule as:
RULE: [Rule text]
REASON: [Why this rule helps]
PATTERN: [Pattern it addresses]""",
        variables=["current_prompt", "patterns", "outcomes"],
        defaults={},
        metadata={"tags": ["meta", "prompt-engineering"]}
    )
]


def create_default_engine(base_path: Optional[Path] = None) -> UnifiedPromptEngine:
    """Create a prompt engine with built-in templates."""
    if base_path is None:
        base_path = Path(".ouroboros")
    
    registry_path = base_path / "prompt_registry.json"
    
    registry = PromptRegistry(registry_path)
    bridge = PromptQueueBridge()
    
    # Register built-in templates if not present
    for template in BUILTIN_TEMPLATES:
        existing = registry.get_latest(template.id)
        if not existing:
            registry.register(template)
    
    return UnifiedPromptEngine(registry, bridge)


# === CLI Interface ===

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Prompt Engine")
    parser.add_argument("command", choices=["list", "stats", "render", "execute"])
    parser.add_argument("--template", help="Template ID")
    parser.add_argument("--vars", help="JSON variables")
    parser.add_argument("--category", help="Filter by category")
    
    args = parser.parse_args()
    
    engine = create_default_engine()
    
    if args.command == "list":
        category = PromptCategory(args.category) if args.category else None
        if category:
            templates = engine.registry.get_by_category(category)
        else:
            templates = list(engine.registry.templates.values())
        
        for t in templates:
            print(f"{t.id}:v{t.version} [{t.category.value}] - {t.description}")
    
    elif args.command == "stats":
        stats = engine.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "render":
        if not args.template:
            print("Error: --template required")
            exit(1)
        
        variables = json.loads(args.vars) if args.vars else {}
        prompt = engine.render_prompt(args.template, variables)
        print(prompt)
    
    elif args.command == "execute":
        if not args.template:
            print("Error: --template required")
            exit(1)
        
        import asyncio
        variables = json.loads(args.vars) if args.vars else {}
        result = asyncio.run(engine.execute_prompt(args.template, variables))
        print(f"Success: {result.success}")
        print(f"Provider: {result.provider}")
        if result.content:
            print(f"Response:\n{result.content[:500]}...")
        if result.error:
            print(f"Error: {result.error}")
