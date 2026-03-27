"""
Recursive Self-Configuration

A MetaPromptEngine that dynamically updates the System Prompt
based on performance history and learned patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum
import json
import re
from collections import Counter


class PatternType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"
    INSIGHT = "insight"
    BEHAVIOR = "behavior"


@dataclass
class Pattern:
    """A detected pattern in performance history."""
    pattern_type: PatternType
    description: str
    frequency: int
    first_seen: datetime
    last_seen: datetime
    examples: list[str] = field(default_factory=list)
    rule_suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type.value,
            "description": self.description,
            "frequency": self.frequency,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "examples": self.examples,
            "rule_suggestion": self.rule_suggestion,
        }


@dataclass
class PromptRule:
    """A rule to inject into the system prompt."""
    id: str
    content: str
    source_pattern: str  # ID of pattern that generated this rule
    created_at: datetime
    active: bool = True
    effectiveness: float = 0.0  # Updated based on outcomes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "source_pattern": self.source_pattern,
            "created_at": self.created_at.isoformat(),
            "active": self.active,
            "effectiveness": self.effectiveness,
        }


@dataclass
class SystemPrompt:
    """The current system prompt configuration."""
    base_prompt: str
    rules: list[PromptRule]
    version: int
    updated_at: datetime

    def render(self) -> str:
        """Render the full system prompt."""
        parts = [self.base_prompt]

        active_rules = [r for r in self.rules if r.active]
        if active_rules:
            parts.append("\n## Learned Rules\n")
            parts.append("Based on past experience, follow these additional guidelines:\n")
            for i, rule in enumerate(active_rules, 1):
                parts.append(f"{i}. {rule.content}\n")

        return "".join(parts)

    def to_dict(self) -> dict:
        return {
            "base_prompt": self.base_prompt,
            "rules": [r.to_dict() for r in self.rules],
            "version": self.version,
            "updated_at": self.updated_at.isoformat(),
        }


class PatternAnalyzer:
    """
    Analyzes performance history to detect patterns.

    Pattern detection strategies:
    - Keyword frequency analysis
    - Failure clustering
    - Success correlation
    - Temporal patterns
    """

    # Failure indicator keywords
    FAILURE_KEYWORDS = [
        "failed", "error", "exception", "crash", "timeout",
        "incorrect", "wrong", "invalid", "broken", "bug",
    ]

    # Success indicator keywords
    SUCCESS_KEYWORDS = [
        "success", "passed", "complete", "working", "improved",
        "optimal", "efficient", "correct", "validated",
    ]

    # Warning indicator keywords
    WARNING_KEYWORDS = [
        "warning", "caution", "slow", "deprecated", "partial",
        "incomplete", "temporary", "workaround", "fragile",
    ]

    def __init__(self):
        self.patterns: list[Pattern] = []

    def analyze_insights(self, insights: list[str]) -> list[Pattern]:
        """
        Analyze recent insights to detect patterns.

        Returns list of detected patterns.
        """
        self.patterns = []

        if len(insights) < 2:
            return self.patterns

        # 1. Keyword frequency analysis
        self._analyze_keywords(insights)

        # 2. Failure pattern detection
        self._analyze_failures(insights)

        # 3. Success pattern detection
        self._analyze_successes(insights)

        # 4. Recurring theme detection
        self._analyze_themes(insights)

        return self.patterns

    def _analyze_keywords(self, insights: list[str]):
        """Analyze keyword frequencies."""
        all_words = []
        for insight in insights:
            words = re.findall(r'\b[a-zA-Z]{4,}\b', insight.lower())
            all_words.extend(words)

        word_counts = Counter(all_words)

        # Find overrepresented keywords
        for word, count in word_counts.most_common(10):
            if count >= 3:  # Appears 3+ times
                # Check if it's a failure word
                if word in self.FAILURE_KEYWORDS:
                    self._add_pattern(
                        PatternType.WARNING,
                        f"Recurring issue with '{word}'",
                        count,
                        insights,
                        f"Avoid actions that lead to {word}",
                    )

    def _analyze_failures(self, insights: list[str]):
        """Detect failure patterns."""
        failure_insights = []
        for insight in insights:
            if any(kw in insight.lower() for kw in self.FAILURE_KEYWORDS):
                failure_insights.append(insight)

        if len(failure_insights) >= 2:
            # Extract common elements from failures
            common_words = self._extract_common_words(failure_insights)
            if common_words:
                self._add_pattern(
                    PatternType.FAILURE,
                    f"Multiple failures related to: {', '.join(common_words[:3])}",
                    len(failure_insights),
                    failure_insights,
                    f"When working with {common_words[0]}, verify thoroughly before proceeding",
                )

    def _analyze_successes(self, insights: list[str]):
        """Detect success patterns."""
        success_insights = []
        for insight in insights:
            if any(kw in insight.lower() for kw in self.SUCCESS_KEYWORDS):
                success_insights.append(insight)

        if len(success_insights) >= 2:
            common_words = self._extract_common_words(success_insights)
            if common_words:
                self._add_pattern(
                    PatternType.SUCCESS,
                    f"Consistent success with: {', '.join(common_words[:3])}",
                    len(success_insights),
                    success_insights,
                    f"Continue using {common_words[0]} approach for similar tasks",
                )

    def _analyze_themes(self, insights: list[str]):
        """Detect recurring themes."""
        # Extract noun phrases (simplified)
        themes = []
        for insight in insights:
            # Find capitalized phrases or quoted strings
            matches = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', insight)
            themes.extend(matches)

        theme_counts = Counter(themes)

        for theme, count in theme_counts.most_common(5):
            if count >= 2:
                self._add_pattern(
                    PatternType.BEHAVIOR,
                    f"Recurring focus on '{theme}'",
                    count,
                    insights,
                    None,  # No rule suggestion for themes
                )

    def _extract_common_words(self, texts: list[str]) -> list[str]:
        """Extract words common across multiple texts."""
        word_sets = []
        for text in texts:
            words = set(re.findall(r'\b[a-zA-Z]{4,}\b', text.lower()))
            word_sets.append(words)

        if not word_sets:
            return []

        # Find intersection
        common = word_sets[0]
        for ws in word_sets[1:]:
            common &= ws

        return list(common)

    def _add_pattern(self, pattern_type: PatternType, description: str,
                     frequency: int, examples: list[str],
                     rule_suggestion: Optional[str]):
        """Add a detected pattern."""
        pattern = Pattern(
            pattern_type=pattern_type,
            description=description,
            frequency=frequency,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            examples=examples[:3],  # Keep 3 examples
            rule_suggestion=rule_suggestion,
        )
        self.patterns.append(pattern)


class MetaPromptEngine:
    """
    Dynamically updates the System Prompt based on performance history.

    Features:
    - Analyzes recent insights for patterns
    - Generates rules from failure patterns
    - Injects rules into system prompt
    - Tracks rule effectiveness
    - Prunes ineffective rules
    """

    DEFAULT_BASE_PROMPT = """You are an AI agent engaged in recursive self-improvement.

Your goal is to continuously improve the ouroboros system through
iterative code modifications, testing, and reflection.

Guidelines:
1. Make incremental, testable changes
2. Always run tests after modifications
3. Document insights for future iterations
4. Rollback changes that degrade performance
"""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.analyzer = PatternAnalyzer()

        self.system_prompt: Optional[SystemPrompt] = None
        self.patterns: list[Pattern] = []
        self.rules: list[PromptRule] = []

        self._load()

    def _load(self):
        """Load saved state."""
        prompt_file = self.state_dir / "system_prompt.json"
        if prompt_file.exists():
            with open(prompt_file) as f:
                data = json.load(f)

            self.rules = [
                PromptRule(
                    id=r["id"],
                    content=r["content"],
                    source_pattern=r["source_pattern"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    active=r.get("active", True),
                    effectiveness=r.get("effectiveness", 0.0),
                )
                for r in data.get("rules", [])
            ]

            self.system_prompt = SystemPrompt(
                base_prompt=data.get("base_prompt", self.DEFAULT_BASE_PROMPT),
                rules=self.rules,
                version=data.get("version", 1),
                updated_at=datetime.fromisoformat(data["updated_at"]),
            )

    def _save(self):
        """Persist state."""
        if not self.system_prompt:
            return

        prompt_file = self.state_dir / "system_prompt.json"
        with open(prompt_file, "w") as f:
            json.dump(self.system_prompt.to_dict(), f, indent=2)

    def update_from_insights(self, insights: list[str]) -> list[PromptRule]:
        """
        Update system prompt based on recent insights.

        Returns list of newly added rules.
        """
        # Analyze patterns
        self.patterns = self.analyzer.analyze_insights(insights)

        new_rules = []

        for pattern in self.patterns:
            # Only create rules from failure and warning patterns
            if pattern.pattern_type in (PatternType.FAILURE, PatternType.WARNING):
                if pattern.rule_suggestion:
                    rule = self._create_rule(pattern)
                    if rule:
                        new_rules.append(rule)

        if new_rules:
            # Update system prompt
            if not self.system_prompt:
                self.system_prompt = SystemPrompt(
                    base_prompt=self.DEFAULT_BASE_PROMPT,
                    rules=[],
                    version=0,
                    updated_at=datetime.now(),
                )

            self.system_prompt.rules.extend(new_rules)
            self.system_prompt.version += 1
            self.system_prompt.updated_at = datetime.now()

            self._save()

        return new_rules

    def _create_rule(self, pattern: Pattern) -> Optional[PromptRule]:
        """Create a rule from a pattern."""
        if not pattern.rule_suggestion:
            return None

        # Check for similar existing rules
        for existing in self.rules:
            if self._similar_rules(existing.content, pattern.rule_suggestion):
                return None

        rule_id = f"RULE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self.rules)}"

        rule = PromptRule(
            id=rule_id,
            content=pattern.rule_suggestion,
            source_pattern=pattern.description,
            created_at=datetime.now(),
        )

        self.rules.append(rule)
        return rule

    def _similar_rules(self, rule1: str, rule2: str) -> bool:
        """Check if two rules are similar."""
        words1 = set(rule1.lower().split())
        words2 = set(rule2.lower().split())

        if not words1 or not words2:
            return False

        overlap = len(words1 & words2) / min(len(words1), len(words2))
        return overlap > 0.7

    def record_rule_effectiveness(self, rule_id: str, effective: bool):
        """Record whether a rule was effective."""
        for rule in self.rules:
            if rule.id == rule_id:
                if effective:
                    rule.effectiveness = min(1.0, rule.effectiveness + 0.1)
                else:
                    rule.effectiveness = max(0.0, rule.effectiveness - 0.2)

                # Deactivate ineffective rules
                if rule.effectiveness < 0.3:
                    rule.active = False

                self._save()
                break

    def prune_ineffective_rules(self, threshold: float = 0.3):
        """Remove or deactivate consistently ineffective rules."""
        pruned = []

        for rule in self.rules:
            if rule.effectiveness < threshold and rule.active:
                rule.active = False
                pruned.append(rule)

        if pruned:
            self._save()

        return pruned

    def get_current_prompt(self) -> str:
        """Get the current system prompt."""
        if not self.system_prompt:
            self.system_prompt = SystemPrompt(
                base_prompt=self.DEFAULT_BASE_PROMPT,
                rules=[],
                version=1,
                updated_at=datetime.now(),
            )

        return self.system_prompt.render()

    def get_statistics(self) -> dict:
        """Get engine statistics."""
        active_rules = [r for r in self.rules if r.active]
        avg_effectiveness = (
            sum(r.effectiveness for r in active_rules) / len(active_rules)
            if active_rules else 0.0
        )

        return {
            "total_rules": len(self.rules),
            "active_rules": len(active_rules),
            "avg_effectiveness": avg_effectiveness,
            "prompt_version": self.system_prompt.version if self.system_prompt else 0,
            "recent_patterns": len(self.patterns),
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    state_dir = Path(".ouroboros/meta")
    state_dir.mkdir(parents=True, exist_ok=True)

    engine = MetaPromptEngine(state_dir)

    # Simulate insights from recent iterations
    insights = [
        "Mocking database in tests is fragile - prefer real connections",
        "However, real connections are slow - use test containers instead",
        "Safety validation must check protected files before any modification",
        "Subprocess isolation provides containment without performance sacrifice",
        "Watchdog should run in separate thread with heartbeat mechanism",
        "High-impact insights should trigger automatic reflection cycles",
        "Reward should weight metric improvement highest (35%)",
        "Generator-Critic architecture enables iterative improvement",
    ]

    print("Analyzing insights...")
    new_rules = engine.update_from_insights(insights)

    print(f"\nDetected {len(new_rules)} new rules:")
    for rule in new_rules:
        print(f"  - {rule.id}: {rule.content}")

    print("\nCurrent System Prompt:")
    print("-" * 50)
    print(engine.get_current_prompt()[:500] + "...")

    print("\nStatistics:")
    print(json.dumps(engine.get_statistics(), indent=2))
