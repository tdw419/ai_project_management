#!/usr/bin/env python3
"""
Prompt Prioritizer - Intelligent Queue Ordering

Determines which prompt should be processed next based on:
- Priority (urgency)
- Confidence (quality)
- Age (freshness)
- Impact (expected value)
- Dependencies (prerequisites)
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import math

CTRM_DB = Path("/home/jericho/zion/projects/ctrm/ctrm/data/truths.db")


class PromptPrioritizer:
    """
    Intelligent prompt prioritization.
    
    Scoring Formula:
    score = (priority_weight / priority) 
          + (confidence * confidence_weight)
          + (age_bonus if fresh)
          + (impact * impact_weight)
    
    Higher score = process first
    """
    
    def __init__(self, db_path: Path = CTRM_DB):
        self.db_path = db_path
        
        # Scoring weights (tunable)
        self.weights = {
            'priority': 5.0,      # Higher = prioritize urgent
            'confidence': 3.0,    # Higher = prioritize quality
            'age': 2.0,           # Higher = prioritize fresh
            'impact': 1.5,        # Higher = prioritize high-impact
        }
        
        # Age thresholds
        self.fresh_hours = 1.0    # < 1 hour = fresh bonus
        self.stale_hours = 24.0   # > 24 hours = stale penalty
    
    def calculate_score(self, prompt: Dict, now: datetime) -> float:
        """
        Calculate priority score for a prompt.
        Higher = should process first.
        """
        # Priority component (inverted - lower priority number = higher score)
        priority = prompt.get('priority', 5)
        priority_score = self.weights['priority'] / priority
        
        # Confidence component
        confidence = prompt.get('ctrm_confidence', 0.5)
        confidence_score = confidence * self.weights['confidence']
        
        # Age component
        age_score = 0.0
        queued_at = prompt.get('queued_at')
        if queued_at:
            try:
                queued_time = datetime.fromisoformat(queued_at.replace('Z', '+00:00'))
                age_hours = (now - queued_time).total_seconds() / 3600
                
                if age_hours < self.fresh_hours:
                    age_score = self.weights['age']  # Fresh bonus
                elif age_hours > self.stale_hours:
                    age_score = -self.weights['age'] * 0.5  # Stale penalty
                else:
                    # Linear decay
                    age_score = self.weights['age'] * (1 - age_hours / self.stale_hours)
            except:
                pass
        
        # Impact component (based on CTRM scores)
        coherent = prompt.get('ctrm_coherent', 0.5)
        actionable = prompt.get('ctrm_actionable', 0.5)
        meaningful = prompt.get('ctrm_meaningful', 0.5)
        impact = (coherent + actionable + meaningful) / 3
        impact_score = impact * self.weights['impact']
        
        # Final score
        total = priority_score + confidence_score + age_score + impact_score
        
        return round(total, 3)
    
    def get_next_prompt(self, limit: int = 10) -> List[Tuple[Dict, float]]:
        """
        Get the next prompts to process, ranked by score.
        
        Returns:
            List of (prompt_dict, score) tuples
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Fetch all pending prompts
        cursor.execute("""
            SELECT id, prompt, priority, status, 
                   ctrm_coherent, ctrm_authentic, ctrm_actionable,
                   ctrm_meaningful, ctrm_grounded, ctrm_confidence,
                   queued_at, source
            FROM prompt_queue
            WHERE status = 'pending'
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        now = datetime.now()
        scored = []
        
        for row in rows:
            prompt = {
                'id': row[0],
                'prompt': row[1],
                'priority': row[2],
                'status': row[3],
                'ctrm_coherent': row[4],
                'ctrm_authentic': row[5],
                'ctrm_actionable': row[6],
                'ctrm_meaningful': row[7],
                'ctrm_grounded': row[8],
                'ctrm_confidence': row[9],
                'queued_at': row[10],
                'source': row[11]
            }
            
            score = self.calculate_score(prompt, now)
            scored.append((prompt, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored[:limit]
    
    def get_next_one(self) -> Optional[Tuple[Dict, float]]:
        """Get the single highest-priority prompt."""
        results = self.get_next_prompt(limit=1)
        return results[0] if results else None
    
    def explain_score(self, prompt: Dict) -> Dict:
        """Explain why a prompt got its score."""
        now = datetime.now()
        
        priority = prompt.get('priority', 5)
        confidence = prompt.get('ctrm_confidence', 0.5)
        
        breakdown = {
            'priority_component': round(self.weights['priority'] / priority, 3),
            'confidence_component': round(confidence * self.weights['confidence'], 3),
            'age_component': 0.0,
            'impact_component': 0.0,
            'total': 0.0
        }
        
        # Age
        queued_at = prompt.get('queued_at')
        if queued_at:
            try:
                queued_time = datetime.fromisoformat(queued_at.replace('Z', '+00:00'))
                age_hours = (now - queued_time).total_seconds() / 3600
                breakdown['age_hours'] = round(age_hours, 2)
                
                if age_hours < self.fresh_hours:
                    breakdown['age_component'] = self.weights['age']
                    breakdown['age_note'] = 'fresh bonus'
                elif age_hours > self.stale_hours:
                    breakdown['age_component'] = -self.weights['age'] * 0.5
                    breakdown['age_note'] = 'stale penalty'
            except:
                pass
        
        # Impact
        coherent = prompt.get('ctrm_coherent', 0.5)
        actionable = prompt.get('ctrm_actionable', 0.5)
        meaningful = prompt.get('ctrm_meaningful', 0.5)
        impact = (coherent + actionable + meaningful) / 3
        breakdown['impact_component'] = round(impact * self.weights['impact'], 3)
        
        # Total
        breakdown['total'] = round(
            breakdown['priority_component'] +
            breakdown['confidence_component'] +
            breakdown['age_component'] +
            breakdown['impact_component'],
            3
        )
        
        return breakdown


class PromptGenerator:
    """
    Generates new prompts based on:
    - System goals
    - Current state analysis
    - Gap detection
    - Previous results
    """
    
    def __init__(self, db_path: Path = CTRM_DB):
        self.db_path = db_path
        
        # Goal templates
        self.goal_templates = [
            "Analyze the current state of {project} and identify improvement opportunities",
            "Implement {feature} in {target}",
            "Fix the issue described in {reference}",
            "Test the changes made to {target}",
            "Document {subject}",
            "Optimize {target} for {metric}",
            "Refactor {target} to improve {quality}",
            "Integrate {component_a} with {component_b}",
            "Debug the error: {error}",
            "Research {topic} and summarize findings"
        ]
    
    def generate_from_results(self, completed_prompt: str, result: str) -> List[str]:
        """Generate follow-up prompts based on a completed prompt's result."""
        new_prompts = []
        result_lower = result.lower()
        
        # Error detection
        if 'error' in result_lower or 'failed' in result_lower:
            new_prompts.append(f"Debug and fix the error encountered in: {completed_prompt[:50]}")
        
        # TODO detection
        if 'todo' in result_lower or 'not implemented' in result_lower:
            new_prompts.append(f"Complete the TODO items from: {completed_prompt[:50]}")
        
        # Test generation
        if 'implement' in completed_prompt.lower() or 'create' in completed_prompt.lower():
            new_prompts.append(f"Write tests for: {completed_prompt[:50]}")
        
        # Documentation
        if 'implement' in completed_prompt.lower():
            new_prompts.append(f"Document the changes from: {completed_prompt[:50]}")
        
        return new_prompts
    
    def generate_from_gaps(self) -> List[str]:
        """Generate prompts by detecting gaps in the system."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        gaps = []
        
        # Check for untested code
        cursor.execute("""
            SELECT COUNT(*) FROM prompt_queue 
            WHERE prompt LIKE '%test%' AND status = 'completed'
        """)
        test_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM prompt_queue 
            WHERE prompt LIKE '%implement%' AND status = 'completed'
        """)
        impl_count = cursor.fetchone()[0]
        
        if impl_count > test_count * 2:
            gaps.append("Test coverage is low - generate tests for recent implementations")
        
        # Check for stale areas
        cursor.execute("""
            SELECT source, MAX(queued_at) as last_update
            FROM prompt_queue
            GROUP BY source
            ORDER BY last_update ASC
            LIMIT 3
        """)
        for row in cursor.fetchall():
            source = row[0]
            if source and source != 'manual':
                gaps.append(f"Review and update {source} - hasn't been processed recently")
        
        conn.close()
        
        return gaps
    
    def generate_proactive(self) -> List[str]:
        """Generate proactive improvement prompts."""
        proactive = [
            "Analyze system performance and identify bottlenecks",
            "Review code quality metrics and suggest improvements",
            "Check for security vulnerabilities in recent changes",
            "Evaluate test coverage and identify gaps",
            "Review documentation completeness",
            "Analyze error patterns in logs",
            "Check for dependency updates",
            "Review resource usage optimization opportunities"
        ]
        return proactive


class AutomatedPromptLoop:
    """
    Fully automated prompt management loop.
    
    Cycle:
    1. PRIORITIZE - Score and rank pending prompts
    2. PROCESS - Execute highest-scored prompt
    3. GENERATE - Create follow-up prompts from result
    4. ENQUEUE - Add new prompts to queue
    5. REPEAT
    """
    
    def __init__(self, db_path: Path = CTRM_DB):
        self.db_path = db_path
        self.prioritizer = PromptPrioritizer(db_path)
        self.generator = PromptGenerator(db_path)
        
    def get_next_to_process(self) -> Optional[Dict]:
        """Get the next prompt to process with full scoring info."""
        result = self.prioritizer.get_next_one()
        if result:
            prompt, score = result
            explanation = self.prioritizer.explain_score(prompt)
            return {
                'prompt': prompt,
                'score': score,
                'explanation': explanation
            }
        return None
    
    def show_next_n(self, n: int = 10):
        """Show the next N prompts ranked by score."""
        scored = self.prioritizer.get_next_prompt(limit=n)
        
        print(f"\n{'='*70}")
        print(f"NEXT {n} PROMPTS TO PROCESS (ranked by priority score)")
        print(f"{'='*70}\n")
        
        for i, (prompt, score) in enumerate(scored, 1):
            text = prompt['prompt'][:60]
            priority = prompt['priority']
            confidence = prompt.get('ctrm_confidence', 0)
            
            print(f"{i:2}. [Score: {score:.2f}] [P{priority}] [Conf: {confidence:.2f}]")
            print(f"    {text}...")
            print()


# === CLI ===

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Prompt Prioritizer")
    parser.add_argument("command", choices=["next", "list", "explain", "gaps", "proactive"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--id", help="Prompt ID to explain")
    
    args = parser.parse_args()
    
    loop = AutomatedPromptLoop()
    
    if args.command == "next":
        result = loop.get_next_to_process()
        if result:
            p = result['prompt']
            e = result['explanation']
            print(f"\n🎯 NEXT PROMPT TO PROCESS")
            print(f"{'='*50}")
            print(f"ID: {p['id']}")
            print(f"Priority: {p['priority']}")
            print(f"Confidence: {p.get('ctrm_confidence', 0):.2f}")
            print(f"Score: {result['score']:.2f}")
            print(f"\nPrompt: {p['prompt'][:200]}...")
            print(f"\n📊 Score Breakdown:")
            for k, v in e.items():
                if k != 'total':
                    print(f"  {k}: {v}")
        else:
            print("No pending prompts")
    
    elif args.command == "list":
        loop.show_next_n(args.limit)
    
    elif args.command == "explain":
        if not args.id:
            print("Error: --id required for explain")
            return
        
        conn = sqlite3.connect(CTRM_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompt_queue WHERE id = ?", (args.id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            prompt = {
                'id': row[0],
                'prompt': row[1],
                'priority': row[3],
                'ctrm_coherent': row[6],
                'ctrm_actionable': row[8],
                'ctrm_meaningful': row[9],
                'ctrm_confidence': row[11],
                'queued_at': row[13]
            }
            prioritizer = PromptPrioritizer()
            explanation = prioritizer.explain_score(prompt)
            print(json.dumps(explanation, indent=2))
        else:
            print(f"Prompt {args.id} not found")
    
    elif args.command == "gaps":
        generator = PromptGenerator()
        gaps = generator.generate_from_gaps()
        print("\n🔍 DETECTED GAPS:")
        for i, gap in enumerate(gaps, 1):
            print(f"  {i}. {gap}")
    
    elif args.command == "proactive":
        generator = PromptGenerator()
        proactive = generator.generate_proactive()
        print("\n🚀 PROACTIVE IMPROVEMENTS:")
        for i, p in enumerate(proactive, 1):
            print(f"  {i}. {p}")


if __name__ == "__main__":
    main()
