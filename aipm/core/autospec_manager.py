"""
AutoSpec Manager - Automates the H/T/M/B hypothesis cycle.
Phase 2.1: Agentic Maturity.

This module provides the logic to identify, formulate, and execute 
empirical experiments based on AI-generated suggestions.
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from aipm.core.unified_prompt_engine import UnifiedPromptEngine, PromptCategory
from aipm.core.simple_bridge import PromptResult

@dataclass
class AutoSpecPlan:
    """A formal experiment plan extracted from AI output."""
    hypothesis: str
    target: str
    metric: str
    budget: int
    code_changes: Dict[str, str]
    original_prompt_id: Optional[str] = None


class AutoSpecManager:
    """
    Manages the lifecycle of AutoSpec experiments within the AIPM loop.
    
    Features:
    - Identify engineering tasks that benefit from empirical testing.
    - Extract H/T/M/B plans from LLM responses.
    - Generate formal hypotheses using the Unified Prompt Engine.
    - Execute experiments via the vendored AutoSpec ExperimentLoop.
    """
    
    def __init__(self, engine: Optional[UnifiedPromptEngine] = None, experiment_loop=None):
        self.engine = engine
        self.experiment_loop = experiment_loop

    def should_run_experiment(self, prompt: str, result: str) -> bool:
        """
        Determines if a prompt/result pair should trigger an AutoSpec experiment.
        
        Criteria:
        1. Engineering keywords in prompt (optimize, refactor, etc.)
        2. Presence of code blocks in result.
        3. Result contains H/T/M/B markers (explicitly requested or not).
        """
        prompt_lower = prompt.lower()
        result_lower = result.lower()
        
        # Explicit markers
        if "h:" in result and "t:" in result:
            return True
            
        # Engineering keywords
        eng_keywords = ['optimize', 'refactor', 'implement', 'fix', 'improve', 'speed up', 'reduce']
        if any(kw in prompt_lower for kw in eng_keywords):
            # Check if result has code
            if '```' in result:
                return True
                
        return False

    def extract_plan(self, content: str, prompt_id: Optional[str] = None) -> Optional[AutoSpecPlan]:
        """
        Extract H/T/M/B plan from text content.
        Supports both formal ASCII spec and simple line-based format.
        """
        # Simple parsing for H/T/M/B
        lines = content.split('\n')
        h, t, m, b = "", "", "", "5"
        
        for line in lines:
            # Clean box drawing characters
            clean_line = re.sub(r'[┌─┐│└┘├┤┬┴┼]', '', line).strip()
            
            if clean_line.startswith('H:'): 
                h = clean_line[2:].strip()
            elif clean_line.startswith('T:'): 
                # Extract target file path (handle <file.py> or file.py)
                raw_target = clean_line[2:].strip()
                t = re.split(r'[\s\(\)]', raw_target.strip("<>"))[0]
            elif clean_line.startswith('M:'): 
                m = clean_line[2:].strip()
            elif clean_line.startswith('B:'): 
                # Try to extract number from B: 5m or B: 5
                b_str = clean_line[2:].strip()
                b_match = re.search(r'(\d+)', b_str)
                if b_match:
                    b = b_match.group(1)
        
        if h and t:
            # Find code block
            # Matches any language identifier or none
            code_match = re.search(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)
            
            if code_match:
                content_code = code_match.group(1).strip()
                # If target is specified, map it
                code_changes = {t: content_code}
                
                return AutoSpecPlan(
                    hypothesis=h,
                    target=t,
                    metric=m or "improvement",
                    budget=int(b),
                    code_changes=code_changes,
                    original_prompt_id=prompt_id
                )
        
        return None

    async def formulate_hypothesis(self, original_task: str, partial_result: str, context: str) -> Optional[AutoSpecPlan]:
        """
        Use the Unified Prompt Engine to turn a vague engineering task 
        into a formal H/T/M/B hypothesis.
        """
        if not self.engine:
            return None
            
        variables = {
            "goal": original_task,
            "success_criteria": "Empirical improvement in targeted metrics",
            "iteration": "1",
            "tree_ascii": "No tree data available",
            "recent_results": f"Partial implementation suggested:\n{partial_result[:500]}...",
            "codebase_context": context
        }
        
        try:
            result = await self.engine.execute_prompt(
                "hypothesis_generation",
                variables=variables
            )
            
            if result.success and result.content:
                return self.extract_plan(result.content)
        except Exception as e:
            print(f"⚠️ Error formulating hypothesis: {e}")
            
        return None

    def run_experiment(self, plan: AutoSpecPlan) -> Dict[str, Any]:
        """
        Executes the experiment using the vendored ExperimentLoop.
        """
        if not self.experiment_loop:
            return {"success": False, "error": "ExperimentLoop not initialized"}
            
        from vendor.autospec.autoresearch.loop import Hypothesis
        
        # Convert to AutoSpec Hypothesis
        hyp = Hypothesis(
            task_id=plan.original_prompt_id or "autonomous_exp",
            description=plan.hypothesis,
            expected_improvement=0.1,
            code_changes=plan.code_changes
        )
        
        print(f"\n🚀 [AutoSpec] Executing Hypothesis: {plan.hypothesis}")
        print(f"   Target: {plan.target} | Metric: {plan.metric} | Budget: {plan.budget} turns")
        
        try:
            # Note: ExperimentLoop.run is synchronous in the current vendor version
            exp_result = self.experiment_loop.run(hyp)
            
            return {
                "success": True,
                "status": exp_result.status.value,
                "metric": exp_result.metric,
                "description": exp_result.description,
                "commit": exp_result.commit_hash
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
