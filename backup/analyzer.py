"""
Response Analyzer - Analyzes LLM responses for quality

Determines if a prompt was completed successfully and generates follow-ups.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import uuid

from aipm.core.engine import Prompt, PromptCategory


class QualityLevel(str, Enum):
    """Quality levels for response analysis"""
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    UNCLEAR = "unclear"


@dataclass
class AnalysisResult:
    """Result of analyzing a response"""
    quality: QualityLevel
    confidence: float
    needs_followup: bool
    reason: str
    success_indicators: List[str]
    failure_indicators: List[str]
    incomplete_indicators: List[str]
    actions_taken: List[str]
    suggested_followups: List[str]


class ResponseAnalyzer:
    """
    Analyzes LLM responses to determine quality and generate follow-ups.
    
    Pattern Detection:
    - Success: complete, done, implemented, fixed, created
    - Failure: error, failed, exception, timeout, panic
    - Incomplete: TODO, FIXME, partial, not done, remaining
    
    Quality Assessment:
    - COMPLETE: Task fully achieved (85%+ confidence)
    - PARTIAL: Progress made, more needed (70%)
    - FAILED: Task crashed or aborted (90%)
    - NEEDS_REVIEW: Done but needs verification (60%)
    - UNCLEAR: Can't determine (40%)
    """
    
    # Success patterns
    SUCCESS_PATTERNS = [
        r"\b(complete[d]?)\b",
        r"\b(done|finished|implemented)\b",
        r"\b(fixed|resolved|solved)\b",
        r"\b(created?|wrote|added)\b",
        r"\b(successfully)\b",
        r"\b(all tests passing)\b",
        r"\b(work[ie]ng)\b",
        r"✅",
    ]
    
    # Failure patterns
    FAILURE_PATTERNS = [
        r"\b(error|exception|panic)\b",
        r"\b(failed|failure)\b",
        r"\b(timeout|timed out)\b",
        r"\b(crash[ed]?)\b",
        r"\b(unable to)\b",
        r"\b(cannot|can't)\b",
        r"❌",
    ]
    
    # Incomplete patterns
    INCOMPLETE_PATTERNS = [
        r"\b(TODO|FIXME|HACK)\b",
        r"\b(partial|partially)\b",
        r"\b(not done|remaining)\b",
        r"\b(still need[s]?)\b",
        r"\b(in progress)\b",
        r"⚠️",
    ]
    
    # Action patterns
    ACTION_PATTERNS = [
        (r"created? file[:\s]+['\"]?([^\s'\"]+)['\"]?", "file_created"),
        (r"wrote tests? for[:\s]+([^\n]+)", "tests_written"),
        (r"fixed bug[s]? in[:\s]+([^\n]+)", "bug_fixed"),
        (r"updated? ([^\n]+)", "updated"),
        (r"removed? ([^\n]+)", "removed"),
    ]
    
    def __init__(
        self,
        complete_threshold: float = 0.85,
        partial_threshold: float = 0.70,
        failed_threshold: float = 0.90,
        review_threshold: float = 0.60,
    ):
        self.complete_threshold = complete_threshold
        self.partial_threshold = partial_threshold
        self.failed_threshold = failed_threshold
        self.review_threshold = review_threshold
    
    def analyze(self, prompt: Prompt) -> AnalysisResult:
        """Analyze a prompt's result"""
        if not prompt.result:
            return AnalysisResult(
                quality=QualityLevel.UNCLEAR,
                confidence=0.0,
                needs_followup=True,
                reason="No result to analyze",
                success_indicators=[],
                failure_indicators=[],
                incomplete_indicators=[],
                actions_taken=[],
                suggested_followups=["Re-run the prompt"],
            )
        
        text = prompt.result.lower()
        
        # Find indicators
        success = self._find_patterns(text, self.SUCCESS_PATTERNS)
        failure = self._find_patterns(text, self.FAILURE_PATTERNS)
        incomplete = self._find_patterns(text, self.INCOMPLETE_PATTERNS)
        actions = self._find_actions(text)
        
        # Calculate quality
        quality, confidence = self._assess_quality(
            success, failure, incomplete, text
        )
        
        # Determine if follow-up needed
        needs_followup = quality in [
            QualityLevel.PARTIAL,
            QualityLevel.FAILED,
            QualityLevel.NEEDS_REVIEW,
        ]
        
        # Generate reason
        reason = self._generate_reason(quality, success, failure, incomplete)
        
        # Generate follow-up suggestions
        suggested = self._generate_suggestions(
            prompt, quality, success, failure, incomplete, actions
        )
        
        return AnalysisResult(
            quality=quality,
            confidence=confidence,
            needs_followup=needs_followup,
            reason=reason,
            success_indicators=success,
            failure_indicators=failure,
            incomplete_indicators=incomplete,
            actions_taken=actions,
            suggested_followups=suggested,
        )
    
    def _find_patterns(self, text: str, patterns: List[str]) -> List[str]:
        """Find all matching patterns in text"""
        found = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                found.extend([m if isinstance(m, str) else m[0] for m in matches])
        return found
    
    def _find_actions(self, text: str) -> List[str]:
        """Find actions taken in the response"""
        actions = []
        for pattern, action_type in self.ACTION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                actions.append(f"{action_type}: {match}")
        return actions
    
    def _assess_quality(
        self,
        success: List[str],
        failure: List[str],
        incomplete: List[str],
        text: str,
    ) -> Tuple[QualityLevel, float]:
        """Assess the quality level of the response"""
        # Count indicators
        s_count = len(success)
        f_count = len(failure)
        i_count = len(incomplete)
        
        # Calculate confidence
        total = s_count + f_count + i_count
        if total == 0:
            return QualityLevel.UNCLEAR, 0.4
        
        # Check for failure first (highest priority)
        if f_count > 0:
            confidence = min(f_count / max(total, 1), 1.0)
            if confidence >= self.failed_threshold:
                return QualityLevel.FAILED, confidence
        
        # Check for incomplete
        if i_count > 0:
            # Has both success and incomplete = needs review
            if s_count > 0:
                return QualityLevel.NEEDS_REVIEW, self.review_threshold
            return QualityLevel.PARTIAL, self.partial_threshold
        
        # Check for complete
        if s_count > 0:
            confidence = min(s_count / max(total, 1), 1.0)
            if confidence >= self.complete_threshold:
                return QualityLevel.COMPLETE, confidence
            return QualityLevel.NEEDS_REVIEW, self.review_threshold
        
        return QualityLevel.UNCLEAR, 0.4
    
    def _generate_reason(
        self,
        quality: QualityLevel,
        success: List[str],
        failure: List[str],
        incomplete: List[str],
    ) -> str:
        """Generate a human-readable reason for the quality assessment"""
        if quality == QualityLevel.COMPLETE:
            return "Task completed successfully"
        elif quality == QualityLevel.FAILED:
            return f"Task failed: {', '.join(failure[:3])}"
        elif quality == QualityLevel.PARTIAL:
            return f"Partial progress: {', '.join(incomplete[:3])}"
        elif quality == QualityLevel.NEEDS_REVIEW:
            return "Needs verification"
        else:
            return "Unable to determine quality"
    
    def _generate_suggestions(
        self,
        prompt: Prompt,
        quality: QualityLevel,
        success: List[str],
        failure: List[str],
        incomplete: List[str],
        actions: List[str],
    ) -> List[str]:
        """Generate suggested follow-up prompts"""
        suggestions = []
        
        if quality == QualityLevel.FAILED:
            suggestions.append(f"Debug and fix the failure in: {prompt.text[:100]}")
        
        if quality == QualityLevel.PARTIAL:
            suggestions.append(f"Continue the work started in: {prompt.text[:100]}")
        
        if incomplete:
            suggestions.append(f"Complete the TODO items from: {prompt.text[:100]}")
        
        if quality == QualityLevel.COMPLETE:
            # Check if tests were written
            has_tests = any("test" in a.lower() for a in actions)
            if not has_tests:
                suggestions.append(f"Write tests for: {prompt.text[:100]}")
            suggestions.append(f"Verify and test the results of: {prompt.text[:100]}")
        
        if quality == QualityLevel.NEEDS_REVIEW:
            suggestions.append(f"Verify and test the results of: {prompt.text[:100]}")
        
        return suggestions[:5]  # Max 5 suggestions
    
    def generate_followups(
        self,
        prompt: Prompt,
        analysis: AnalysisResult,
    ) -> List[Prompt]:
        """Generate follow-up prompts based on analysis"""
        followups = []
        
        for suggestion in analysis.suggested_followups:
            # Create a lower-priority follow-up
            followup = Prompt(
                id=f"followup_{uuid.uuid4().hex[:8]}",
                text=suggestion,
                category=prompt.category,
                priority=min(prompt.priority + 1, 10),  # Lower priority
                confidence=0.5,
                impact=0.5,
                parent_id=prompt.id,
            )
            followups.append(followup)
        
        return followups
