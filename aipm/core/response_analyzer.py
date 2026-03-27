#!/usr/bin/env python3
"""
Prompt Response Analyzer

Analyzes completed prompt results to:
1. Determine if the task was actually completed
2. Identify issues that need follow-up
3. Generate intelligent new prompts based on response content

Quality Indicators:
- Success markers: "complete", "done", "implemented", "fixed"
- Failure markers: "error", "failed", "exception", "timeout"
- Incomplete markers: "TODO", "FIXME", "partial", "not implemented"
- Action markers: specific actions taken (files modified, tests written)
"""

import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from aipm.config import CTRM_DB


class ResponseQuality(Enum):
    COMPLETE = "complete"           # Task fully done
    PARTIAL = "partial"             # Some work done, more needed
    FAILED = "failed"               # Task failed
    UNCLEAR = "unclear"             # Can't determine
    NEEDS_REVIEW = "needs_review"   # Done but needs verification


@dataclass
class AnalysisResult:
    """Result of analyzing a prompt response."""
    prompt_id: str
    prompt: str
    result: str
    quality: ResponseQuality
    confidence: float
    
    # What was found
    success_indicators: List[str]
    failure_indicators: List[str]
    incomplete_indicators: List[str]
    actions_taken: List[str]
    
    # What needs to happen
    needs_followup: bool
    followup_reason: str
    
    # Generated prompts
    suggested_prompts: List[str]
    
    # Metadata
    analysis_timestamp: str


class PromptResponseAnalyzer:
    """
    Analyzes completed prompt results to determine quality
    and generate intelligent follow-ups.
    """
    
    def __init__(self, db_path: Path = CTRM_DB):
        self.db_path = db_path
        
        # Success indicators (task completed)
        self.success_patterns = [
            r'\b(complete[ds]?)\b',
            r'\b(done|finished)\b',
            r'\b(implemented|created|built)\b',
            r'\b(fixed|resolved|solved)\b',
            r'\b(success[ful]*)\b',
            r'\b(working|works)\b',
            r'\b(tests? passed)\b',
            r'\b(all\s+\d+\s+tests?\s+pass)',
            r'\b✅',
            r'\bverified\b',
        ]
        
        # Failure indicators (task failed)
        self.failure_patterns = [
            r'\b(error|exception|crash)\b',
            r'\b(failed|failure)\b',
            r'\b(timeout|timed out)\b',
            r'\b(cannot|can\'t|unable)\b',
            r'\b(not\s+possible|impossible)\b',
            r'\b❌',
            r'\b(panic|fatal)\b',
        ]
        
        # Incomplete indicators (more work needed)
        self.incomplete_patterns = [
            r'\b(TODO|FIXME|XXX|HACK)\b',
            r'\b(partial|partially)\b',
            r'\b(not\s+(yet|implemented|done|complete))\b',
            r'\b(remaining|still\s+need)\b',
            r'\b(next\s+step|future\s+work)\b',
            r'\b(in\s+progress|wip)\b',
            r'\b(placeholder|stub)\b',
        ]
        
        # Action patterns (what was done)
        self.action_patterns = [
            (r'(?:created?|wrote?|added?)\s+(?:the\s+)?(?:file\s+)?[`\'"]?([^\s`\'"]+\.[a-z]+)', 'file_created'),
            (r'(?:modified|updated?|edited)\s+(?:the\s+)?(?:file\s+)?[`\'"]?([^\s`\'"]+\.[a-z]+)', 'file_modified'),
            (r'(?:deleted?|removed?)\s+(?:the\s+)?(?:file\s+)?[`\'"]?([^\s`\'"]+\.[a-z]+)', 'file_deleted'),
            (r'(?:wrote?|added?|created?)\s+(\d+)\s+tests?', 'tests_written'),
            (r'(?:fixed|resolved)\s+(\d+)\s+(?:issues?|bugs?|errors?)', 'bugs_fixed'),
            (r'(?:added?|implemented)\s+(\w+)\s+(?:feature|function|method)', 'feature_added'),
        ]
    
    def analyze_response(self, prompt_id: str) -> Optional[AnalysisResult]:
        """
        Analyze a completed prompt's result.
        
        Returns AnalysisResult with quality assessment and suggested follow-ups.
        """
        # Fetch the prompt and result
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, prompt, result, ctrm_confidence
            FROM prompt_queue
            WHERE id = ? AND status = 'completed'
        """, (prompt_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        prompt_id, prompt, result, confidence = row
        
        if not result:
            result = ""
        
        result_lower = result.lower()
        
        # Find all indicators
        success_found = []
        for pattern in self.success_patterns:
            matches = re.findall(pattern, result_lower)
            success_found.extend(matches)
        
        failure_found = []
        for pattern in self.failure_patterns:
            matches = re.findall(pattern, result_lower)
            failure_found.extend(matches)
        
        incomplete_found = []
        for pattern in self.incomplete_patterns:
            matches = re.findall(pattern, result_lower)
            incomplete_found.extend(matches)
        
        # Find actions taken
        actions = []
        for pattern, action_type in self.action_patterns:
            matches = re.findall(pattern, result_lower)
            for match in matches:
                actions.append(f"{action_type}: {match}")
        
        # Determine quality
        quality, quality_confidence = self._determine_quality(
            success_found, failure_found, incomplete_found, actions
        )
        
        # Determine if follow-up needed
        needs_followup, followup_reason = self._needs_followup(
            quality, failure_found, incomplete_found, actions
        )
        
        # Generate suggested prompts
        suggested = self._generate_followups(
            prompt, result, quality, failure_found, incomplete_found, actions
        )
        
        return AnalysisResult(
            prompt_id=prompt_id,
            prompt=prompt,
            result=result[:500],  # Truncate for storage
            quality=quality,
            confidence=quality_confidence,
            success_indicators=success_found[:5],
            failure_indicators=failure_found[:5],
            incomplete_indicators=incomplete_found[:5],
            actions_taken=actions[:5],
            needs_followup=needs_followup,
            followup_reason=followup_reason,
            suggested_prompts=suggested,
            analysis_timestamp=datetime.now().isoformat()
        )
    
    def _determine_quality(self, success: List, failure: List, 
                           incomplete: List, actions: List) -> Tuple[ResponseQuality, float]:
        """Determine response quality based on indicators."""
        
        success_count = len(success)
        failure_count = len(failure)
        incomplete_count = len(incomplete)
        action_count = len(actions)
        
        # Calculate scores
        success_score = success_count * 2 + action_count
        failure_score = failure_count * 3
        incomplete_score = incomplete_count * 1.5
        
        total = success_score - failure_score - incomplete_score
        
        # Determine quality
        if failure_count > 0 and success_count == 0:
            return ResponseQuality.FAILED, 0.9
        
        if incomplete_count > 2 and success_count == 0:
            return ResponseQuality.PARTIAL, 0.7
        
        if total >= 3:
            return ResponseQuality.COMPLETE, 0.85
        
        if total >= 1:
            return ResponseQuality.NEEDS_REVIEW, 0.6
        
        if total >= -1:
            return ResponseQuality.UNCLEAR, 0.4
        
        return ResponseQuality.PARTIAL, 0.5
    
    def _needs_followup(self, quality: ResponseQuality, 
                        failure: List, incomplete: List, 
                        actions: List) -> Tuple[bool, str]:
        """Determine if follow-up is needed."""
        
        if quality == ResponseQuality.FAILED:
            return True, "Task failed - needs debugging"
        
        if quality == ResponseQuality.PARTIAL:
            return True, "Task partially complete - needs continuation"
        
        if len(incomplete) > 0:
            return True, f"Found {len(incomplete)} incomplete markers"
        
        if quality == ResponseQuality.NEEDS_REVIEW:
            return True, "Needs verification"
        
        if len(actions) == 0:
            return True, "No clear actions taken - may need clarification"
        
        return False, "Task appears complete"
    
    def _generate_followups(self, prompt: str, result: str,
                            quality: ResponseQuality,
                            failure: List, incomplete: List,
                            actions: List) -> List[str]:
        """Generate intelligent follow-up prompts based on analysis."""
        
        followups = []
        prompt_lower = prompt.lower()
        
        # If failed, generate debugging prompt
        if quality == ResponseQuality.FAILED:
            followups.append(
                f"Debug and fix the failure in: {prompt[:80]}"
            )
        
        # If partial, generate continuation prompt
        if quality == ResponseQuality.PARTIAL:
            followups.append(
                f"Continue the work started in: {prompt[:80]}"
            )
        
        # For each incomplete marker, generate specific follow-up
        for marker in incomplete[:2]:
            if 'TODO' in marker.upper():
                followups.append(
                    f"Complete the TODO items from: {prompt[:60]}"
                )
            elif 'FIXME' in marker.upper():
                followups.append(
                    f"Fix the issues marked FIXME in: {prompt[:60]}"
                )
        
        # If tests were mentioned but not written
        if 'test' in prompt_lower and not any('test' in a for a in actions):
            followups.append(
                f"Write tests for: {prompt[:70]}"
            )
        
        # If implementation was done but no docs
        if any('implement' in p or 'create' in p for p in [prompt_lower]) and \
           not any('doc' in a.lower() for a in actions):
            followups.append(
                f"Document the changes from: {prompt[:60]}"
            )
        
        # If errors were encountered
        if 'error' in result.lower():
            followups.append(
                f"Investigate and resolve errors from: {prompt[:60]}"
            )
        
        # If verification needed
        if quality == ResponseQuality.NEEDS_REVIEW:
            followups.append(
                f"Verify and test the results of: {prompt[:60]}"
            )
        
        return followups[:5]  # Limit to 5
    
    def analyze_all_completed(self, limit: int = 20) -> List[AnalysisResult]:
        """Analyze all recently completed prompts."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM prompt_queue
            WHERE status = 'completed'
            ORDER BY completed_at DESC
            LIMIT ?
        """, (limit,))
        
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        results = []
        for pid in ids:
            analysis = self.analyze_response(pid)
            if analysis:
                results.append(analysis)
        
        return results
    
    def get_summary(self) -> Dict:
        """Get summary of all completed prompts."""
        analyses = self.analyze_all_completed(limit=100)
        
        if not analyses:
            return {"total": 0}
        
        by_quality = {}
        needs_followup = 0
        total_suggested = 0
        
        for a in analyses:
            q = a.quality.value
            by_quality[q] = by_quality.get(q, 0) + 1
            
            if a.needs_followup:
                needs_followup += 1
            
            total_suggested += len(a.suggested_prompts)
        
        return {
            "total_analyzed": len(analyses),
            "by_quality": by_quality,
            "needs_followup": needs_followup,
            "total_suggested_prompts": total_suggested,
            "avg_confidence": sum(a.confidence for a in analyses) / len(analyses)
        }
    
    def store_analysis(self, analysis: AnalysisResult):
        """Store analysis result back to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update the prompt record with analysis
        cursor.execute("""
            UPDATE prompt_queue
            SET verification_notes = ?
            WHERE id = ?
        """, (f"Quality: {analysis.quality.value}, Followup: {analysis.needs_followup}",
              analysis.prompt_id))
        
        conn.commit()
        conn.close()
    
    def enqueue_followups(self, analysis: AnalysisResult, 
                          priority_offset: int = 1) -> int:
        """Enqueue suggested follow-up prompts."""
        if not analysis.suggested_prompts:
            return 0
        
        from ouroboros.core.ctrm_prompt_manager import CTRMPromptManager
        manager = CTRMPromptManager(self.db_path)
        
        # Determine priority (lower than parent)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT priority FROM prompt_queue WHERE id = ?", 
                      (analysis.prompt_id,))
        row = cursor.fetchone()
        conn.close()
        
        parent_priority = row[0] if row else 5
        new_priority = min(10, parent_priority + priority_offset)
        
        count = 0
        for prompt in analysis.suggested_prompts:
            manager.enqueue(
                prompt,
                priority=new_priority,
                source=f"analysis:{analysis.prompt_id}"
            )
            count += 1
        
        return count


# === CLI ===

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Prompt Response Analyzer")
    parser.add_argument("command", choices=["analyze", "recent", "summary", "followups"])
    parser.add_argument("--id", help="Prompt ID to analyze")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--enqueue", action="store_true", help="Enqueue follow-ups")
    
    args = parser.parse_args()
    
    analyzer = PromptResponseAnalyzer()
    
    if args.command == "analyze":
        if not args.id:
            print("Error: --id required for analyze")
            return
        
        result = analyzer.analyze_response(args.id)
        if result:
            print(f"\n{'='*60}")
            print(f"ANALYSIS: {result.prompt_id}")
            print(f"{'='*60}")
            print(f"\nQuality: {result.quality.value.upper()} (confidence: {result.confidence:.0%})")
            print(f"Needs follow-up: {result.needs_followup}")
            print(f"Reason: {result.followup_reason}")
            
            if result.success_indicators:
                print(f"\n✅ Success indicators: {result.success_indicators}")
            if result.failure_indicators:
                print(f"\n❌ Failure indicators: {result.failure_indicators}")
            if result.incomplete_indicators:
                print(f"\n⚠️  Incomplete indicators: {result.incomplete_indicators}")
            if result.actions_taken:
                print(f"\n🔧 Actions taken: {result.actions_taken}")
            
            if result.suggested_prompts:
                print(f"\n📝 Suggested follow-ups:")
                for i, p in enumerate(result.suggested_prompts, 1):
                    print(f"   {i}. {p}")
            
            if args.enqueue and result.suggested_prompts:
                count = analyzer.enqueue_followups(result)
                print(f"\n📤 Enqueued {count} follow-up prompts")
        else:
            print(f"Prompt {args.id} not found or not completed")
    
    elif args.command == "recent":
        results = analyzer.analyze_all_completed(limit=args.limit)
        
        print(f"\n{'='*70}")
        print(f"RECENT COMPLETED PROMPTS (analyzed)")
        print(f"{'='*70}\n")
        
        for i, r in enumerate(results, 1):
            quality_icon = {
                'complete': '✅',
                'partial': '◐',
                'failed': '❌',
                'unclear': '❓',
                'needs_review': '🔍'
            }.get(r.quality.value, '❓')
            
            print(f"{i:2}. {quality_icon} [{r.quality.value:12}] {r.prompt[:50]}...")
            if r.needs_followup:
                print(f"    └─ Needs: {r.followup_reason}")
    
    elif args.command == "summary":
        summary = analyzer.get_summary()
        print(json.dumps(summary, indent=2))
    
    elif args.command == "followups":
        results = analyzer.analyze_all_completed(limit=args.limit)
        
        all_followups = []
        for r in results:
            if r.needs_followup:
                all_followups.extend(r.suggested_prompts)
        
        print(f"\n{'='*70}")
        print(f"SUGGESTED FOLLOW-UPS ({len(all_followups)} total)")
        print(f"{'='*70}\n")
        
        for i, p in enumerate(all_followups[:20], 1):
            print(f"{i:2}. {p}")


if __name__ == "__main__":
    main()
