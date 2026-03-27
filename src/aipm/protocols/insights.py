"""
Knowledge Representation & Dynamic Heuristics

A versioned insights database with novelty/conflict scoring and
automatic reflection scheduling for high-impact insights.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum
import json
import hashlib
import math


class InsightImpact(Enum):
    LOW = "low"           # Minor observation
    MEDIUM = "medium"     # Useful pattern
    HIGH = "high"         # Significant discovery
    CRITICAL = "critical" # Paradigm shift


class ConflictType(Enum):
    CONTRADICTION = "contradiction"    # Directly opposes existing insight
    REFINEMENT = "refinement"          # Narrows or clarifies existing
    GENERALIZATION = "generalization"  # Broadens existing
    INDEPENDENT = "independent"        # No conflict


@dataclass
class Insight:
    """A learned insight with metadata."""
    id: str
    content: str
    created_at: datetime
    version: int = 1
    impact: InsightImpact = InsightImpact.MEDIUM
    confidence: float = 0.5
    source_iteration: int = 0
    tags: list[str] = field(default_factory=list)
    supersedes: Optional[str] = None  # ID of insight this replaces

    def content_hash(self) -> str:
        """Hash of content for deduplication."""
        return hashlib.md5(self.content.encode()).hexdigest()[:8]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "impact": self.impact.value,
            "confidence": self.confidence,
            "source_iteration": self.source_iteration,
            "tags": self.tags,
            "supersedes": self.supersedes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Insight":
        return cls(
            id=data["id"],
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            version=data.get("version", 1),
            impact=InsightImpact(data.get("impact", "medium")),
            confidence=data.get("confidence", 0.5),
            source_iteration=data.get("source_iteration", 0),
            tags=data.get("tags", []),
            supersedes=data.get("supersedes"),
        )


@dataclass
class HeuristicScore:
    """Result of heuristic evaluation."""
    novelty_score: float      # 0-1, how new is this insight?
    conflict_score: float     # 0-1, how much does it conflict?
    impact_score: float       # 0-1, combined importance
    conflict_type: ConflictType
    conflicting_with: list[str] = field(default_factory=list)  # IDs of conflicting insights
    should_reflect: bool = False
    reason: str = ""


class InsightHeuristics:
    """
    Heuristic algorithms for scoring insights.

    Scoring factors:
    - Novelty: Semantic distance from existing insights
    - Conflict: Contradiction or refinement of existing beliefs
    - Impact: Potential to change behavior
    """

    # Keywords that indicate high impact
    HIGH_IMPACT_KEYWORDS = [
        "safety", "critical", "fundamental", "paradigm",
        "breakthrough", "essential", "root cause",
    ]

    # Keywords that indicate contradictions
    CONTRADICTION_KEYWORDS = [
        "however", "but", "contrary", "opposite",
        "wrong", "incorrect", "failed", "not",
    ]

    def __init__(self, insights_db: "InsightsDatabase"):
        self.db = insights_db

    def score_novelty(self, insight: Insight) -> float:
        """
        Calculate novelty score based on semantic distance.

        Uses simple heuristics:
        - Word overlap with existing insights
        - Content hash uniqueness
        - Tag novelty
        """
        existing = self.db.get_all_insights()

        if not existing:
            return 1.0  # First insight is maximally novel

        # Calculate word overlap with each existing insight
        insight_words = set(insight.content.lower().split())

        max_overlap = 0.0
        for existing_insight in existing:
            existing_words = set(existing_insight.content.lower().split())
            if not existing_words or not insight_words:
                continue

            overlap = len(insight_words & existing_words) / max(len(insight_words), len(existing_words))
            max_overlap = max(max_overlap, overlap)

        # Novelty is inverse of max overlap
        novelty = 1.0 - max_overlap

        # Bonus for new tags
        existing_tags = set()
        for e in existing:
            existing_tags.update(e.tags)
        new_tags = set(insight.tags) - existing_tags
        tag_bonus = len(new_tags) * 0.1

        return min(1.0, novelty + tag_bonus)

    def detect_conflicts(self, insight: Insight) -> tuple[ConflictType, list[str]]:
        """
        Detect conflicts with existing insights.

        Returns conflict type and list of conflicting insight IDs.
        """
        existing = self.db.get_all_insights()
        conflicting_ids = []
        conflict_type = ConflictType.INDEPENDENT

        insight_lower = insight.content.lower()

        # Check for contradiction keywords
        has_contradiction = any(kw in insight_lower for kw in self.CONTRADICTION_KEYWORDS)

        for existing_insight in existing:
            existing_lower = existing_insight.content.lower()
            existing_words = set(existing_lower.split())
            insight_words = set(insight_lower.split())

            # Check for semantic overlap
            overlap = len(insight_words & existing_words) / max(len(insight_words), len(existing_words), 1)

            if overlap > 0.3:  # Significant overlap
                if has_contradiction:
                    conflict_type = ConflictType.CONTRADICTION
                    conflicting_ids.append(existing_insight.id)
                elif overlap > 0.7:
                    conflict_type = ConflictType.REFINEMENT
                    conflicting_ids.append(existing_insight.id)
                elif len(insight_words) > len(existing_words) * 1.5:
                    conflict_type = ConflictType.GENERALIZATION
                    conflicting_ids.append(existing_insight.id)

        return conflict_type, conflicting_ids

    def score_impact(self, insight: Insight, novelty: float, conflict_type: ConflictType) -> float:
        """
        Calculate overall impact score.

        Factors:
        - Novelty (high novelty = high potential impact)
        - Conflict type (contradictions are high impact)
        - Keywords (certain terms indicate importance)
        - Confidence level
        """
        score = 0.0

        # Novelty contribution
        score += novelty * 0.3

        # Conflict contribution
        conflict_weights = {
            ConflictType.INDEPENDENT: 0.1,
            ConflictType.GENERALIZATION: 0.2,
            ConflictType.REFINEMENT: 0.3,
            ConflictType.CONTRADICTION: 0.5,
        }
        score += conflict_weights.get(conflict_type, 0.1)

        # Keyword contribution
        insight_lower = insight.content.lower()
        keyword_hits = sum(1 for kw in self.HIGH_IMPACT_KEYWORDS if kw in insight_lower)
        score += min(0.3, keyword_hits * 0.1)

        # Confidence contribution
        score += insight.confidence * 0.1

        return min(1.0, score)

    def evaluate(self, insight: Insight) -> HeuristicScore:
        """
        Run full heuristic evaluation on an insight.
        """
        # Calculate scores
        novelty = self.score_novelty(insight)
        conflict_type, conflicting_with = self.detect_conflicts(insight)
        impact = self.score_impact(insight, novelty, conflict_type)

        # Determine conflict score
        conflict_score = len(conflicting_with) * 0.2 if conflicting_with else 0.0

        # Should we trigger reflection?
        should_reflect = (
            impact > 0.7 or
            conflict_type == ConflictType.CONTRADICTION or
            novelty > 0.9
        )

        reason = self._generate_reason(novelty, conflict_type, impact, should_reflect)

        return HeuristicScore(
            novelty_score=novelty,
            conflict_score=conflict_score,
            impact_score=impact,
            conflict_type=conflict_type,
            conflicting_with=conflicting_with,
            should_reflect=should_reflect,
            reason=reason,
        )

    def _generate_reason(self, novelty: float, conflict: ConflictType,
                         impact: float, reflect: bool) -> str:
        """Generate human-readable reason for the score."""
        parts = []

        if novelty > 0.8:
            parts.append(f"High novelty ({novelty:.2f})")
        elif novelty > 0.5:
            parts.append(f"Moderate novelty ({novelty:.2f})")

        if conflict != ConflictType.INDEPENDENT:
            parts.append(f"Conflict type: {conflict.value}")

        if impact > 0.7:
            parts.append(f"High impact ({impact:.2f})")

        if reflect:
            parts.append("→ Reflection recommended")

        return " | ".join(parts) if parts else "Standard insight"


class InsightsDatabase:
    """
    Versioned database for insights with conflict tracking.

    Features:
    - Add new insights with automatic scoring
    - Track insight versions and supersessions
    - Detect and resolve conflicts
    - Schedule reflection for high-impact insights
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.insights: list[Insight] = []
        self.heuristics = InsightHeuristics(self)
        self.reflection_queue: list[str] = []  # IDs of insights needing reflection
        self._load()

    def _load(self):
        """Load database from disk."""
        if not self.db_path.exists():
            return

        with open(self.db_path) as f:
            data = json.load(f)

        self.insights = [Insight.from_dict(i) for i in data.get("insights", [])]
        self.reflection_queue = data.get("reflection_queue", [])

    def _save(self):
        """Persist database to disk."""
        data = {
            "insights": [i.to_dict() for i in self.insights],
            "reflection_queue": self.reflection_queue,
            "version": 1,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_all_insights(self) -> list[Insight]:
        """Get all active insights."""
        return [i for i in self.insights if i.supersedes is None or
                not any(e.id == i.supersedes for e in self.insights)]

    def add_insight(self, content: str, tags: list[str] = None,
                    source_iteration: int = 0) -> tuple[Insight, HeuristicScore]:
        """
        Add a new insight with automatic scoring.

        Returns the insight and its heuristic score.
        """
        # Create insight
        timestamp = datetime.now()
        id_hash = hashlib.md5(f"{content}{timestamp}".encode()).hexdigest()[:8]
        insight_id = f"INS-{timestamp.strftime('%Y%m%d')}-{id_hash}"

        insight = Insight(
            id=insight_id,
            content=content,
            created_at=timestamp,
            tags=tags or [],
            source_iteration=source_iteration,
        )

        # Evaluate with heuristics
        score = self.heuristics.evaluate(insight)

        # Set impact based on score
        if score.impact_score > 0.8:
            insight.impact = InsightImpact.CRITICAL
        elif score.impact_score > 0.6:
            insight.impact = InsightImpact.HIGH
        elif score.impact_score > 0.4:
            insight.impact = InsightImpact.MEDIUM
        else:
            insight.impact = InsightImpact.LOW

        # Handle conflicts
        if score.conflict_type == ConflictType.CONTRADICTION:
            # Mark conflicting insights as superseded
            for conflict_id in score.conflicting_with:
                insight.supersedes = conflict_id
                break  # Only supersede one

        # Add to database
        self.insights.append(insight)

        # Queue for reflection if needed
        if score.should_reflect:
            self.reflection_queue.append(insight.id)

        self._save()

        return insight, score

    def process_reflection_queue(self) -> list[Insight]:
        """
        Process insights queued for reflection.

        Returns insights that need reflection cycles.
        """
        to_reflect = []
        for insight_id in self.reflection_queue:
            insight = next((i for i in self.insights if i.id == insight_id), None)
            if insight:
                to_reflect.append(insight)

        return to_reflect

    def clear_reflection_queue(self):
        """Clear the reflection queue after processing."""
        self.reflection_queue = []
        self._save()

    def get_statistics(self) -> dict:
        """Get database statistics."""
        active = self.get_all_insights()

        by_impact = {}
        for i in active:
            impact = i.impact.value
            by_impact[impact] = by_impact.get(impact, 0) + 1

        return {
            "total_insights": len(self.insights),
            "active_insights": len(active),
            "reflection_pending": len(self.reflection_queue),
            "by_impact": by_impact,
            "avg_confidence": sum(i.confidence for i in active) / len(active) if active else 0,
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    db_path = Path(".ouroboros/insights_db.json")
    db_path.parent.mkdir(exist_ok=True)

    db = InsightsDatabase(db_path)

    # Add some insights
    insights = [
        ("Mocking database in tests is fragile - prefer real connections", ["testing", "reliability"]),
        ("However, real connections are slow - use test containers instead", ["testing", "performance"]),
        ("Safety validation must check protected files before any modification", ["safety", "architecture"]),
        ("Subprocess isolation provides containment without performance sacrifice", ["safety", "performance"]),
    ]

    for content, tags in insights:
        insight, score = db.add_insight(content, tags)
        print(f"\n📌 {insight.id}: {content[:50]}...")
        print(f"   Novelty: {score.novelty_score:.2f}")
        print(f"   Impact: {score.impact_score:.2f}")
        print(f"   Conflict: {score.conflict_type.value}")
        print(f"   Reason: {score.reason}")

    # Check statistics
    print("\n" + "=" * 50)
    stats = db.get_statistics()
    print(f"Database stats: {stats}")

    # Check reflection queue
    print(f"\nReflection queue: {len(db.reflection_queue)} pending")
    for insight in db.process_reflection_queue():
        print(f"  - {insight.id}: {insight.content[:50]}...")
