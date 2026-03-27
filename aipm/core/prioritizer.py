"""
Prompt Prioritizer - Intelligent scoring of prompts

Uses multiple factors to determine which prompt should be processed next:
- Urgency (Priority)
- Quality (Confidence)
- Freshness (Age)
- Expected Impact
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from aipm.core.engine import Prompt


class PromptPrioritizer:
    """
    Calculates priority scores for prompts.
    
    Formula:
        score = (5.0 / priority) + (confidence × 3.0) + age_bonus + (impact × 1.5)
    
    Where:
        - priority: 1 (urgent) to 10 (low priority)
        - confidence: 0.0 to 1.0 (quality of the prompt)
        - age_bonus: +2.0 for fresh (<1h), -1.0 for stale (>24h)
        - impact: 0.0 to 1.0 (expected value)
    """
    
    def __init__(
        self,
        urgency_weight: float = 5.0,
        quality_weight: float = 3.0,
        impact_weight: float = 1.5,
        fresh_bonus: float = 2.0,
        stale_penalty: float = -1.0,
        fresh_threshold_hours: float = 1.0,
        stale_threshold_hours: float = 24.0,
    ):
        self.urgency_weight = urgency_weight
        self.quality_weight = quality_weight
        self.impact_weight = impact_weight
        self.fresh_bonus = fresh_bonus
        self.stale_penalty = stale_penalty
        self.fresh_threshold = timedelta(hours=fresh_threshold_hours)
        self.stale_threshold = timedelta(hours=stale_threshold_hours)
    
    def score(self, prompt: Prompt) -> float:
        """Calculate the priority score for a prompt"""
        now = datetime.now()
        age = now - prompt.created_at
        
        # Urgency component (inverted priority)
        urgency = self.urgency_weight / max(prompt.priority, 1)
        
        # Quality component
        quality = prompt.confidence * self.quality_weight
        
        # Freshness bonus/penalty
        if age < self.fresh_threshold:
            freshness = self.fresh_bonus
        elif age > self.stale_threshold:
            freshness = self.stale_penalty
        else:
            freshness = 0.0
        
        # Impact component
        impact = prompt.impact * self.impact_weight
        
        return urgency + quality + freshness + impact
    
    def rank(self, prompts: List[Prompt]) -> List[Tuple[Prompt, float]]:
        """Rank prompts by score (highest first)"""
        scored = [(p, self.score(p)) for p in prompts]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def get_top(self, prompts: List[Prompt], n: int = 10) -> List[Tuple[Prompt, float]]:
        """Get the top N prompts by score"""
        return self.rank(prompts)[:n]
    
    def get_next(self, prompts: List[Prompt]) -> Tuple[Prompt, float]:
        """Get the highest-scoring prompt"""
        ranked = self.rank(prompts)
        if ranked:
            return ranked[0]
        raise ValueError("No prompts to rank")
    
    def get_score_breakdown(self, prompt: Prompt) -> Dict[str, float]:
        """Get a breakdown of the score components"""
        now = datetime.now()
        age = now - prompt.created_at
        
        urgency = self.urgency_weight / max(prompt.priority, 1)
        quality = prompt.confidence * self.quality_weight
        
        if age < self.fresh_threshold:
            freshness = self.fresh_bonus
            freshness_reason = "fresh"
        elif age > self.stale_threshold:
            freshness = self.stale_penalty
            freshness_reason = "stale"
        else:
            freshness = 0.0
            freshness_reason = "normal"
        
        impact = prompt.impact * self.impact_weight
        
        return {
            "urgency": urgency,
            "quality": quality,
            "freshness": freshness,
            "freshness_reason": freshness_reason,
            "impact": impact,
            "total": urgency + quality + freshness + impact,
        }
