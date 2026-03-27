#!/usr/bin/env python3
"""
CTRM Prompt Manager - Unified Prompt Management

Uses CTRM database as backend for truth-based scoring
Multi-provider queue
Template engine
ASCII World integration
"""

import sqlite3
import json
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import CTRM database
CTRM_DB = Path("/home/jericho/zion/projects/ctrm/ctrm/data/truths.db")


class CTRMPromptManager:
    """
    Manages prompts using CTRM as the backend.
    
    Features:
    - Store prompts in CTRM prompt_queue table
    - Score with CTRM metrics (coherent, authentic, actionable, meaningful, grounded)
    - Process through multi-provider queue
    - Generate new prompts based on results
    - ASCII World integration
    """
    
    def __init__(self, db_path: Path = CTRM_DB):
        self.db_path = db_path
        # Will use queue bridge from unified engine
        # Will use semantic_analyzer from Ouroboros
        
    def _get_connection(self):
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    # === Queue Operations ===
    
    def enqueue(self, prompt: str, priority: int = 5, 
                    source: str = "manual",
                    metadata: Optional[Dict] = None) -> str:
        """Add a prompt to the queue with CTRM scoring."""
        prompt_id = f"prompt_{hashlib.md5(prompt.encode()).hexdigest()[:8]}"
        now = datetime.now().isoformat()
        
        # Calculate CTRM scores
        scores = self._calculate_ctrm_scores(prompt)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO prompt_queue 
                (id, prompt, source, priority, status, queued_at,
                 ctrm_coherent, ctrm_authentic, ctrm_actionable,
                 ctrm_meaningful, ctrm_grounded, ctrm_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (prompt_id, prompt, source, priority, 'pending', 
             now, scores['coherent'], scores['authentic'], 
             scores['actionable'], scores['meaningful'], scores['grounded'], 
             scores['confidence']))
            
        return prompt_id
    
    def dequeue(self, status: str = "pending", 
                   priority: Optional[int] = None,
                   limit: int = 1) -> List[Dict]:
        """
        Get next prompt from queue.
        
        Args:
            status: Filter by status ('pending', 'processing', 'completed')
            priority: Minimum priority (1-10, lower = higher)
            limit: Maximum prompts to return
        
        Returns:
            List of prompts matching criteria
        """
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT id, prompt, priority, status, ctrm_confidence, queued_at
                FROM prompt_queue
                WHERE status = ?
                ORDER BY priority ASC, ctrm_confidence DESC
                LIMIT ?
            """
            conn.execute(query, (status, priority, limit))
            
            rows = conn.fetchall()
            
            return [
                {
                    'id': row[0],
                    'prompt': row[1],
                    'priority': row[2],
                    'status': row[3],
                    'confidence': row[4],
                    'queued_at': row[5]
                }
                for row in rows
            ]
    
    def mark_processing(self, prompt_id: str) -> bool:
        """Mark a prompt as being processed."""
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE prompt_queue 
            SET status = 'processing', processed_at = ?
            WHERE id = ?
        """, (now, prompt_id))
        
        rowcount = cursor.rowcount
        conn.commit()
        conn.close()
        
        return rowcount > 0
    
    def complete(self, prompt_id: str, result: str,
                    verified: bool = False, notes: str = "") -> bool:
        """Mark a prompt as completed with result."""
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE prompt_queue 
            SET status = 'completed', 
                completed_at = ?,
                result = ?,
                result_verified = ?,
                verification_notes = ?
            WHERE id = ?
        """, (now, result, int(verified), notes, prompt_id))
        
        conn.commit()
        conn.close()
        
        return True
    
    # === Processing ===
    
    async def process_next(self, provider_preference: Optional[str] = None) -> Optional[Dict]:
        """
        Process the next prompt from the queue.
        
        1. Dequeue next pending prompt
        2. Mark as processing
        3. Execute via queue bridge
        4. Mark as completed
        5. Generate follow-up prompts
        
        Returns:
            {
                'prompt_id': str,
                'prompt': str,
                'result': PromptResult,
                'new_prompts': List[str]
            }
        """
        # Get next prompt
        prompts = self.dequeue(status='pending', limit=1)
        
        if not prompts:
            return None
        
        prompt = prompts[0]
        prompt_id = prompt['id']
        prompt_text = prompt['prompt']
        
        # Mark as processing
        self.mark_processing(prompt_id)
        
        # Execute via queue bridge
        result = await self.bridge.process_prompt_async(
            prompt_text,
            priority=prompt['priority'],
            preferred_provider=provider_preference
        )
        
        # Mark as completed
        self.complete(
            prompt_id,
            result.content or "",
            verified=result.success,
            notes=f"Processed via {result.provider}"
        )
        
        # Generate follow-up prompts
        new_prompts = await self._generate_followups(prompt_text, result)
        
        return {
            'prompt_id': prompt_id,
            'prompt': prompt_text,
            'result': result,
            'new_prompts': new_prompts
        }
    
    def _calculate_ctrm_scores(self, prompt: str) -> Dict[str, float]:
        """Calculate CTRM scores for a prompt."""
        # Coherent: Is the logically consistent?
        coherent = self._score_coherent(prompt)
        
        # Authentic: Is the genuine/original?
        authentic = self._score_authentic(prompt)
        
        # Actionable: Can something be done?
        actionable = self._score_actionable(prompt)
        
        # Meaningful: Does it matter?
        meaningful = self._score_meaningful(prompt)
        
        # Grounded: Is this based in reality?
        grounded = self._score_grounded(prompt)
        
        # Combined confidence
        confidence = (coherent + authentic + actionable + meaningful + grounded) / 5
        
        return {
            'coherent': coherent,
            'authentic': authentic,
            'actionable': actionable,
            'meaningful': meaningful,
            'grounded': grounded,
            'confidence': confidence
        }
    
    def _score_coherent(self, prompt: str) -> float:
        """Score coherence (logical consistency)."""
        # Check for clear structure
        score = 0.5
        
        if '?' in prompt or 'what' in prompt.lower():
            score += 0.1  # Questions need answers
        if 'how' in prompt.lower():
            score += 0.1  # How implies method
        if 'implement' in prompt.lower() or 'create' in prompt.lower():
            score += 0.1  # Clear action
        if len(prompt.split()) > 3:
            score += 0.1  # Multiple parts
        
        return min(score, 1.0)
    
    def _score_authentic(self, prompt: str) -> float:
        """Score authenticity (originality)."""
        # Check for personal/specific context
        score = 0.5
        
        if any(word in prompt.lower() for word in ['my', 'our', 'i need', 'we should']):
            score += 0.1  # Personal context
        if '/' in prompt or '~' in prompt:
            score += 0.1  # File paths
        if len(prompt) > 50:
            score += 0.1  # Detailed
        
        return min(score, 1.0)
    
    def _score_actionable(self, prompt: str) -> float:
        """Score actionability (can something be done?)."""
        score = 0.5
        
        # Check for action verbs
        action_verbs = ['implement', 'create', 'fix', 'add', 'update', 'improve', 'build', 'write', 'test']
        for verb in action_verbs:
            if verb in prompt.lower():
                score += 0.1
        
        # Check for clear target
        if '/' in prompt and ('.' in prompt or '_' in prompt):
            score += 0.1
        
        return min(score, 1.0)
    
    def _score_meaningful(self, prompt: str) -> float:
        """Score meaningfulness (does it matter?)."""
        score = 0.5
        
        # Check for impact words
        impact_words = ['important', 'critical', 'necessary', 'essential', 'priority']
        for word in impact_words:
            if word in prompt.lower():
                score += 0.1
        
        # Check for project context
        if any(p in prompt.lower() for p in ['ctrm', 'ouroboros', 'geometry', 'system']):
            score += 0.1
        
        return min(score, 1.0)
    
    def _score_grounded(self, prompt: str) -> float:
        """Score groundedness (based in reality)."""
        score = 0.5
        
        # Check for concrete references
        if '/' in prompt:
            score += 0.1  # File path
        if 'http' in prompt or 'localhost' in prompt:
            score += 0.1  # URL
        if any(c in prompt for c in '0123456789'):
            score += 0.05  # Numbers
        
        return min(score, 1.0)
    
    async def _generate_followups(self, original_prompt: str, 
                                      result) -> List[str]:
        """Generate follow-up prompts based on result."""
        if not result.success:
            return ["Retry with different approach"]
        
        followups = []
        original_lower = original_prompt.lower()
        
        # Check for errors that need handling
        if 'error' in result.content.lower() or 'failed' in result.content.lower():
            followups.append("Investigate and fix the error encountered")
        
        # Check for incomplete work
        if 'todo' in result.content.lower() or 'not implemented' in result.content.lower():
            followups.append("Complete the partial implementation")
        
        # Check for tests
        if 'test' in original_lower:
            followups.append("Run tests to verify changes")
        
        # Check for documentation
        if 'implement' in original_lower or 'create' in original_lower:
            followups.append("Document the changes")
        
        return followups[:3]  # Limit to 3 follow-ups
    
    # === Statistics ===
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        stats = {}
        
        # Count by status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM prompt_queue
            GROUP BY status
        """)
        for row in cursor.fetchall():
            stats[f"{row[0]}_count"] = row[1]
        
        # Average confidence by status
        cursor.execute("""
            SELECT status, AVG(ctrm_confidence) as avg_confidence
            FROM prompt_queue
            GROUP BY status
        """)
        for row in cursor.fetchall():
            stats[f"{row[0]}_avg_confidence"] = row[1]
        
        # Top priorities
        cursor.execute("""
            SELECT priority, COUNT(*) as count
            FROM prompt_queue
            WHERE status = 'pending'
            GROUP BY priority
            ORDER BY count DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            stats[f"priority_{row[0]}_count"] = row[1]
        
        conn.close()
        return stats
    
    def get_next_n(self, n: int = 10, status: str = "pending") -> List[Dict]:
        """Get next N prompts from queue."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                SELECT id, prompt, priority, ctrm_confidence, queued_at
                FROM prompt_queue
                WHERE status = ?
                ORDER BY priority ASC, ctrm_confidence DESC
                LIMIT ?
            """, (status, n))
            
            return [dict(row) for row in conn.fetchall()]


# === CLI Interface ===

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="CTRM Prompt Manager")
    parser.add_argument("command", choices=["status", "next", "enqueue", "process", "stats"])
    parser.add_argument("--prompt", help="Prompt text (for enqueue)")
    parser.add_argument("--priority", type=int, default=5, help="Priority 1-10")
    parser.add_argument("--limit", type=int, default=10, help="Limit for next/list")
    parser.add_argument("--provider", default="auto", help="Preferred provider")
    
    args = parser.parse_args()
    
    manager = CTRMPromptManager()
    
    if args.command == "status":
        stats = manager.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "next":
        prompts = manager.get_next_n(args.limit)
        for p in prompts:
            print(f"[{p['priority']}] {p['prompt'][:60]}...")
    
    elif args.command == "enqueue":
        if not args.prompt:
            print("Error: --prompt required for enqueue")
            exit(1)
        prompt_id = manager.enqueue(args.prompt, priority=args.priority)
        print(f"Enqueued: {prompt_id}")
    
    elif args.command == "process":
        result = asyncio.run(manager.process_next(provider_preference=args.provider))
        if result:
            print(f"Processed: {result['prompt_id']}")
            print(f"Success: {result['result'].success}")
            if result['new_prompts']:
                print(f"Generated {len(result['new_prompts'])} follow-up prompts")
        else:
            print("No pending prompts")
    
    elif args.command == "stats":
        stats = manager.get_stats()
        print(f"Pending: {stats.get('pending_count', 0)}")
        print(f"Processing: {stats.get('processing_count', 0)}")
        print(f"Completed: {stats.get('completed_count', 0)}")
        for key, value in stats.items():
            if 'confidence' in key:
                print(f"{key}: {value:.2f}")


if __name__ == "__main__":
    main()
