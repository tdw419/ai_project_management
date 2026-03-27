"""
Self-Prompt Generator - V2 with Unified Engine Integration

Generates the next hypothesis/experiment based on past results.
Uses the unified prompt engine for multi-provider support and analytics.

This is the "brain" that reads feedback and decides what to try next.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
import os
import re
import json

# Import unified engine components
try:
    from .unified_prompt_engine import (
        UnifiedPromptEngine, PromptRegistry, ContextProvider,
        PromptCategory, create_default_engine
    )
    from .queue_bridge import PromptQueueBridge, PromptResult
    from ..protocols.semantic_analyzer import SemanticAnalyzer
    HAS_UNIFIED_ENGINE = True
except ImportError:
    HAS_UNIFIED_ENGINE = False


@dataclass
class ExperimentSpec:
    """ASCII experiment specification that the body can execute."""

    hypothesis: str  # H: What we're testing
    target: str  # T: File(s) to modify
    metric: str  # M: Success criteria
    budget: str  # B: Time budget
    code_changes: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_ascii(self) -> str:
        """Convert to ASCII spec format."""
        code_status = "Included" if self.code_changes else "None"
        decision = self.metadata.get("decision", "REFINE")
        return f"""┌───────────────────────────────────────┐
│ DECISION: {decision:<27} │
├───────────────────────────────────────┤
│ H: {self.hypothesis:<34} │
│ T: {self.target:<34} │
│ M: {self.metric:<34} │
│ B: {self.budget:<34} │
│ CODE: {code_status:<32} │
├───────────────────────────────────────┤
│ FLOW: HYP → RUN → EVAL → DECIDE       │
└───────────────────────────────────────┘"""


class SelfPromptGenerator:
    """
    Generates the next experiment by:
    1. Reading the results log (past attempts)
    2. Reading the experiment tree (flowchart of paths)
    3. Reading the goal state (what we're trying to achieve)
    4. Using the unified prompt engine for LLM calls
    5. Applying semantic analysis for pattern-aware decisions
    """

    SYSTEM_PROMPT = """You are an autonomous research strategist in a recursive self-improvement loop.

Your role is to:
1. Analyze the EXPERIMENT FLOWCHART (the tree of attempted paths).
2. Decide whether to:
   - REFINE: Continue improving the current best branch.
   - PIVOT: If the current branch is flatlining (no improvement), go back to a previous node and try a different approach.
   - HALT: If the goal is met or impossible.
3. Generate the next hypothesis and exact code changes.

You output decisions in ASCII spec format:
┌───────────────────────────────────────┐
│ DECISION: <REFINE | PIVOT node_id>    │
├───────────────────────────────────────┤
│ H: <hypothesis - what to test>        │
│ T: <target - file(s) to modify>       │
│ M: <metric - success criteria>        │
│ B: <budget - time limit>              │
├───────────────────────────────────────┤
│ FLOW: HYP → RUN → EVAL → DECIDE       │
└───────────────────────────────────────┘

After the ASCII block, provide the full content of the target file in a markdown code block.

If PIVOTING, explain why the current path failed and why the new path is better.
"""

    def __init__(self, 
                 model: str = "claude-sonnet-4-6-20250514",
                 use_unified_engine: bool = True,
                 project_root: Optional[Path] = None):
        self.model = model
        self.project_root = project_root or Path.cwd()
        
        # Initialize unified engine if available and requested
        self.engine: Optional[UnifiedPromptEngine] = None
        self.semantic_analyzer: Optional[SemanticAnalyzer] = None
        
        if use_unified_engine and HAS_UNIFIED_ENGINE:
            try:
                self.engine = create_default_engine(self.project_root / ".ouroboros")
                self.semantic_analyzer = SemanticAnalyzer(self.project_root / ".ouroboros" / "semantic")
            except Exception as e:
                print(f"Warning: Failed to initialize unified engine: {e}")
        
        # Fallback to direct Anthropic if no unified engine
        self.use_mock = not os.getenv("ANTHROPIC_API_KEY") and self.engine is None
        if not self.use_mock and self.engine is None:
            import anthropic
            self.client = anthropic.Anthropic()

    def generate_next(
        self,
        goal: str,
        success_criteria: str,
        results_tsv: Optional[Path] = None,
        codebase_context: Optional[str] = None,
        tree_ascii: Optional[str] = None,
    ) -> ExperimentSpec:
        """
        Generate the next experiment based on goal, results, and tree structure.
        
        Uses unified engine if available, otherwise falls back to direct API.
        """
        # Get learned rules from semantic analyzer
        learned_rules = ""
        if self.semantic_analyzer:
            rules = self.semantic_analyzer.get_rules()
            if rules:
                learned_rules = "\n".join(f"- {r}" for r in rules[:10])
        
        # If we have the unified engine, use it
        if self.engine:
            return self._generate_with_engine(
                goal, success_criteria, results_tsv, codebase_context, tree_ascii, learned_rules
            )
        
        # Fallback to mock or direct API
        if self.use_mock:
            return self._generate_mock(goal, results_tsv)
        
        return self._generate_with_anthropic(
            goal, success_criteria, results_tsv, codebase_context, tree_ascii
        )

    def _generate_with_engine(
        self,
        goal: str,
        success_criteria: str,
        results_tsv: Optional[Path],
        codebase_context: Optional[str],
        tree_ascii: Optional[str],
        learned_rules: str
    ) -> ExperimentSpec:
        """Generate using unified prompt engine with async support."""
        import asyncio
        
        # Build context
        results_context = ""
        if results_tsv and results_tsv.exists():
            with open(results_tsv) as f:
                results_context = f.read()
        
        # Set context for template
        self.engine.context.set("goal", goal)
        self.engine.context.set("success_criteria", success_criteria)
        self.engine.context.set("tree_ascii", tree_ascii or "No tree data")
        self.engine.context.set("recent_results", results_context or "No results yet")
        self.engine.context.set("codebase_context", codebase_context or "No context")
        self.engine.context.set("learned_rules", learned_rules or "No rules yet")
        
        # Read iteration count
        iteration = 0
        if results_tsv and results_tsv.exists():
            with open(results_tsv) as f:
                iteration = len(f.readlines()) - 1
        self.engine.context.set("iteration", str(iteration + 1))
        
        try:
            # Execute via unified engine (async)
            result = asyncio.run(self.engine.execute_prompt(
                "hypothesis_generation",
                track_outcome=True
            ))
            
            if result.success and result.content:
                return self._parse_response(result.content)
            
            # Fallback to mock on failure
            print(f"Warning: Engine returned unsuccessful result: {result.error}")
            return self._generate_mock(goal, results_tsv)
            
        except Exception as e:
            print(f"Warning: Engine execution failed: {e}")
            return self._generate_mock(goal, results_tsv)

    def _generate_with_anthropic(
        self,
        goal: str,
        success_criteria: str,
        results_tsv: Optional[Path],
        codebase_context: Optional[str],
        tree_ascii: Optional[str]
    ) -> ExperimentSpec:
        """Generate using direct Anthropic API (fallback)."""
        results_context = ""
        if results_tsv and results_tsv.exists():
            with open(results_tsv) as f:
                results_context = f"\n\nPAST RESULTS:\n{f.read()}"

        tree_context = f"\n\nEXPERIMENT FLOWCHART:\n{tree_ascii}" if tree_ascii else ""
        code_context = f"\n\nCODEBASE CONTEXT:\n{codebase_context}" if codebase_context else ""

        prompt = f"""GOAL: {goal}
SUCCESS CRITERIA: {success_criteria}{tree_context}{results_context}{code_context}

Based on the flowchart and results, should we REFINE the current path or PIVOT?
Generate the next experiment spec and code."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_response(response.content[0].text)

    def _generate_mock(self, goal: str, results_tsv: Optional[Path]) -> ExperimentSpec:
        """Generate a mock hypothesis for testing without API key."""
        iteration = 0
        if results_tsv and results_tsv.exists():
            with open(results_tsv) as f:
                iteration = len(f.readlines()) - 1

        hypotheses = [
            "Increase iterations in Leibniz formula",
            "Use Archimedes method for pi",
            "Implement Nilakantha series",
            "Use math.pi directly",
        ]
        
        target = "pi_approximator.py"
        idx = min(iteration, len(hypotheses) - 1)
        
        mock_codes = [
            "# Leibniz improvement mock code\ndef approximate_pi(): return 3.1415",
            "# Archimedes mock code\ndef approximate_pi(): return 3.14159",
            "# Nilakantha mock code\ndef approximate_pi(): return 3.141592",
            "import math\ndef approximate_pi(): return math.pi"
        ]

        if "Improve the pi approximation" in goal:
            spec = ExperimentSpec(
                hypothesis=hypotheses[idx],
                target=target,
                metric="error < 0.0001",
                budget="1m",
                code_changes={target: mock_codes[idx]}
            )
            spec.metadata["decision"] = "REFINE"
            return spec
        
        spec = ExperimentSpec(
            hypothesis=f"Mock hypothesis {iteration + 1}",
            target="unknown.py",
            metric="improvement",
            budget="1m",
            code_changes={"unknown.py": "# Mock content"}
        )
        spec.metadata["decision"] = "REFINE"
        return spec

    def _parse_response(self, response: str) -> ExperimentSpec:
        """Parse ASCII spec and code block from LLM response."""
        print(f"DEBUG: LLM Response:\n{response}")
        
        # Extract Decision
        decision_match = re.search(r"DECISION:\s*(.+?)\s*[│\n]", response)
        decision = decision_match.group(1).strip() if decision_match else "REFINE"

        # Extract lines starting with H:, T:, M:, B:
        lines = response.split("\n")

        hypothesis = ""
        target = ""
        metric = ""
        budget = "5m"

        for line in lines:
            line = line.strip(" │\t")
            if line.startswith("H:"):
                hypothesis = line[2:].strip()
            elif line.startswith("T:"):
                raw_target = line[2:].strip()
                target = re.split(r'[\s\(\)]', raw_target.strip("<>"))[0]
            elif line.startswith("M:"):
                raw_metric = line[2:].strip()
                metric = raw_metric.split("(")[0].strip()
            elif line.startswith("B:"):
                budget = line[2:].strip().split("(")[0].strip()

        # Extract code block
        code_changes = {}
        if target:
            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if not code_match:
                code_match = re.search(r"```(?:\w+)?\n(.*?)```", response, re.DOTALL)
                
            if code_match:
                content = code_match.group(1).strip()
                box_chars_re = r'[┌─┐│└┘├┤┬┴┼]'
                lines = content.split("\n")
                cleaned_lines = []
                for line in lines:
                    cleaned_line = re.sub(box_chars_re, '', line)
                    if line.strip() and not cleaned_line.strip():
                        continue
                    cleaned_lines.append(cleaned_line)
                
                code_changes[target] = "\n".join(cleaned_lines)

        spec = ExperimentSpec(
            hypothesis=hypothesis or "No hypothesis generated",
            target=target or "unknown.py",
            metric=metric or "improvement",
            budget=budget,
            code_changes=code_changes
        )
        spec.metadata["decision"] = decision
        return spec
    
    def record_outcome(self, action_type: str, metric_before: float, 
                       metric_after: float, success: bool = True):
        """Record an outcome for semantic analysis."""
        if self.semantic_analyzer:
            self.semantic_analyzer.record_action(
                action_type=action_type,
                action_detail=f"Metric: {metric_before} -> {metric_after}",
                metric_before=metric_before,
                metric_after=metric_after,
                event_success=success
            )
    
    def get_learned_rules(self) -> List[str]:
        """Get learned rules from semantic analysis."""
        if self.semantic_analyzer:
            return self.semantic_analyzer.get_rules()
        return []


# === Backward Compatibility ===

# Old import path still works
SelfPrompter = SelfPromptGenerator
