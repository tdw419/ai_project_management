"""
Semantic Pattern Analyzer

Detects patterns in code and outcomes using:
- Code structure analysis (not just keywords)
- Anti-pattern detection
- Metric correlation analysis
- Temporal pattern detection
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from pathlib import Path
import re
import json
from collections import Counter


class PatternSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PatternType(Enum):
    ANTI_PATTERN = "anti_pattern"
    BEST_PRACTICE = "best_practice"
    CORRELATION = "correlation"
    TEMPORAL = "temporal"
    BEHAVIOR = "behavior"
    INSIGHT = "insight"


@dataclass
class SemanticPattern:
    """A detected semantic pattern."""
    pattern_type: PatternType
    name: str
    description: str
    severity: PatternSeverity
    confidence: float  # 0.0 to 1.0
    occurrences: int
    examples: List[str]
    suggested_rule: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type.value,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "occurrences": self.occurrences,
            "examples": self.examples[:5],
            "suggested_rule": self.suggested_rule,
            "metadata": self.metadata,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None
        }


# === Anti-Pattern Definitions ===

ANTI_PATTERNS = [
    {
        "name": "retry_loop_without_backoff",
        "pattern": r"while.*(?:retry|attempt).*:\s*\n.*(?:sleep|wait)\s*\(\s*\d+\s*\)",
        "description": "Retry loop with fixed delay instead of exponential backoff",
        "rule": "Use exponential backoff for retries: delay = base_delay * (2 ** attempt)",
        "severity": PatternSeverity.WARNING
    },
    {
        "name": "hardcoded_timeout",
        "pattern": r"(?:timeout|delay|sleep|wait)\s*[=:]\s*\d+(?!\s*\*|\s*\+)",
        "description": "Hardcoded timeout value without configuration",
        "rule": "Make timeouts configurable via environment variables or config",
        "severity": PatternSeverity.INFO
    },
    {
        "name": "silent_exception",
        "pattern": r"except\s+\w+.*:\s*\n\s*pass",
        "description": "Silent exception handling that swallows errors",
        "rule": "At minimum, log exceptions before passing: logger.debug(f'Handled: {e}')",
        "severity": PatternSeverity.WARNING
    },
    {
        "name": "bare_except",
        "pattern": r"except\s*:\s*\n",
        "description": "Bare except clause catches everything including KeyboardInterrupt",
        "rule": "Use 'except Exception as e:' to avoid catching system exceptions",
        "severity": PatternSeverity.ERROR
    },
    {
        "name": "mutable_default_arg",
        "pattern": r"def\s+\w+\s*\([^)]*=\s*(?:\[\]|\{\}|set\(\))",
        "description": "Mutable default argument (list/dict) shared across calls",
        "rule": "Use None as default and initialize inside function",
        "severity": PatternSeverity.WARNING
    },
    {
        "name": "sql_injection_risk",
        "pattern": r"(?:execute|executemany)\s*\([^)]*%[sd][^)]*\)",
        "description": "Potential SQL injection via string formatting",
        "rule": "Use parameterized queries: cursor.execute(sql, params)",
        "severity": PatternSeverity.CRITICAL
    },
    {
        "name": "print_in_production",
        "pattern": r"^\s*print\s*\(",
        "description": "print() statements in production code",
        "rule": "Use logging module instead of print() for production",
        "severity": PatternSeverity.INFO
    },
    {
        "name": "todo_without_issue",
        "pattern": r"#\s*TODO(?!\s*#\d+)",
        "description": "TODO comment without issue reference",
        "rule": "Link TODOs to issues: TODO #123 - description",
        "severity": PatternSeverity.INFO
    },
    {
        "name": "deeply_nested",
        "pattern": r"(?:if|for|while|with).*:\s*(?:\n\s+(?:if|for|while|with)){4,}",
        "description": "Deeply nested code (4+ levels)",
        "rule": "Extract nested logic into separate functions or use early returns",
        "severity": PatternSeverity.WARNING
    },
    {
        "name": "long_function",
        "pattern": r"def\s+\w+\s*\([^)]*\):(?:(?!\ndef\s).){500,}",
        "description": "Function exceeds 500 characters without a break",
        "rule": "Break large functions into smaller, focused functions",
        "severity": PatternSeverity.INFO
    }
]


# === Best Practice Patterns ===

BEST_PRACTICES = [
    {
        "name": "type_hints",
        "pattern": r"def\s+\w+\s*\([^)]*\)\s*->\s*\w+",
        "description": "Function with return type hint",
        "rule": "Continue using type hints for better IDE support and documentation",
        "severity": PatternSeverity.INFO
    },
    {
        "name": "docstring",
        "pattern": r'"""[\s\S]*?"""',
        "description": "Docstring documentation",
        "rule": "Keep docstrings updated and include examples for complex functions",
        "severity": PatternSeverity.INFO
    },
    {
        "name": "context_manager",
        "pattern": r"with\s+\w+.*as\s+\w+",
        "description": "Using context manager for resource handling",
        "rule": "Prefer context managers for files, connections, locks",
        "severity": PatternSeverity.INFO
    },
    {
        "name": "fstring",
        "pattern": r'f["\'][^"\']*\{[^}]+\}',
        "description": "Using f-strings for formatting",
        "rule": "f-strings are preferred for readability and performance",
        "severity": PatternSeverity.INFO
    }
]


class CodeAnalyzer:
    """Analyzes code for patterns using AST and regex."""
    
    def __init__(self):
        self.patterns: List[SemanticPattern] = []
    
    def analyze(self, code: str, filename: str = "unknown") -> List[SemanticPattern]:
        """
        Analyze code for all pattern types.
        
        Returns list of detected patterns.
        """
        self.patterns = []
        
        # Check anti-patterns
        self._check_patterns(code, filename, ANTI_PATTERNS, PatternType.ANTI_PATTERN)
        
        # Check best practices
        self._check_patterns(code, filename, BEST_PRACTICES, PatternType.BEST_PRACTICE)
        
        # Check structure patterns
        self._check_structure(code, filename)
        
        return self.patterns
    
    def _check_patterns(self, code: str, filename: str, 
                       patterns_def: List[dict], pattern_type: PatternType):
        """Check code against pattern definitions."""
        for pdef in patterns_def:
            matches = list(re.finditer(pdef["pattern"], code, re.MULTILINE))
            
            if matches:
                examples = []
                for m in matches[:5]:
                    # Extract context around match
                    start = max(0, m.start() - 20)
                    end = min(len(code), m.end() + 20)
                    examples.append(code[start:end].replace("\n", "\\n"))
                
                pattern = SemanticPattern(
                    pattern_type=pattern_type,
                    name=pdef["name"],
                    description=pdef["description"],
                    severity=pdef["severity"],
                    confidence=min(len(matches) / 5.0, 1.0),
                    occurrences=len(matches),
                    examples=examples,
                    suggested_rule=pdef.get("rule"),
                    metadata={"filename": filename},
                    first_seen=datetime.now(),
                    last_seen=datetime.now()
                )
                self.patterns.append(pattern)
    
    def _check_structure(self, code: str, filename: str):
        """Check structural patterns."""
        lines = code.split("\n")
        
        # Check line length
        long_lines = [(i+1, len(line)) for i, line in enumerate(lines) if len(line) > 100]
        if len(long_lines) > 5:
            self.patterns.append(SemanticPattern(
                pattern_type=PatternType.BEHAVIOR,
                name="long_lines",
                description=f"Many lines exceed 100 characters ({len(long_lines)} lines)",
                severity=PatternSeverity.INFO,
                confidence=0.7,
                occurrences=len(long_lines),
                examples=[f"Line {n}: {l} chars" for n, l in long_lines[:5]],
                suggested_rule="Keep lines under 100 characters for readability",
                metadata={"filename": filename}
            ))
        
        # Check for complex conditionals
        complex_ifs = [line for line in lines if line.strip().startswith("if ") and line.count("and") + line.count("or") > 2]
        if complex_ifs:
            self.patterns.append(SemanticPattern(
                pattern_type=PatternType.BEHAVIOR,
                name="complex_condition",
                description="Complex conditional with multiple and/or operators",
                severity=PatternSeverity.INFO,
                confidence=0.6,
                occurrences=len(complex_ifs),
                examples=complex_ifs[:5],
                suggested_rule="Extract complex conditions into named variables or functions",
                metadata={"filename": filename}
            ))


class MetricCorrelationAnalyzer:
    """Analyzes correlations between actions and metric changes."""
    
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
    
    def add_entry(self, action_type: str, action_detail: str, 
                  metric_before: float, metric_after: float,
                  metadata: Optional[Dict] = None):
        """Add an entry to history."""
        self.history.append({
            "action_type": action_type,
            "action_detail": action_detail,
            "metric_before": metric_before,
            "metric_after": metric_after,
            "metric_change": metric_after - metric_before,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
    
    def analyze(self) -> List[SemanticPattern]:
        """Find correlations between actions and metric changes."""
        patterns = []
        
        if len(self.history) < 3:
            return patterns
        
        # Group by action type
        by_action: Dict[str, List[Dict]] = {}
        for entry in self.history:
            action = entry["action_type"]
            if action not in by_action:
                by_action[action] = []
            by_action[action].append(entry)
        
        # Find actions with consistent improvement
        for action, entries in by_action.items():
            if len(entries) < 3:
                continue
            
            improvements = [e for e in entries if e["metric_change"] > 0]
            regressions = [e for e in entries if e["metric_change"] < 0]
            
            improvement_rate = len(improvements) / len(entries)
            avg_change = sum(e["metric_change"] for e in entries) / len(entries)
            
            if improvement_rate >= 0.7 and avg_change > 0:
                patterns.append(SemanticPattern(
                    pattern_type=PatternType.CORRELATION,
                    name=f"action_improves_{action}",
                    description=f"'{action}' consistently improves metrics ({improvement_rate:.0%} success)",
                    severity=PatternSeverity.INFO,
                    confidence=improvement_rate,
                    occurrences=len(entries),
                    examples=[f"+{e['metric_change']:.4f}: {e['action_detail'][:50]}" for e in improvements[:5]],
                    suggested_rule=f"Prefer '{action}' when optimizing - {improvement_rate:.0%} success rate",
                    metadata={"avg_change": avg_change, "improvement_rate": improvement_rate}
                ))
            
            elif improvement_rate <= 0.3 and avg_change < 0:
                patterns.append(SemanticPattern(
                    pattern_type=PatternType.CORRELATION,
                    name=f"action_regresses_{action}",
                    description=f"'{action}' often regresses metrics ({(1-improvement_rate):.0%} failure)",
                    severity=PatternSeverity.WARNING,
                    confidence=1 - improvement_rate,
                    occurrences=len(entries),
                    examples=[f"{e['metric_change']:.4f}: {e['action_detail'][:50]}" for e in regressions[:5]],
                    suggested_rule=f"Be cautious with '{action}' - often causes regressions",
                    metadata={"avg_change": avg_change, "regression_rate": 1 - improvement_rate}
                ))
        
        return patterns
    
    def save(self, path: Path):
        """Save history to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.history, f, indent=2)
    
    def load(self, path: Path):
        """Load history from file."""
        if path.exists():
            with open(path) as f:
                self.history = json.load(f)


class TemporalPatternAnalyzer:
    """Detects time-based patterns in behavior."""
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
    
    def add_event(self, event_type: str, detail: str, 
                  success: bool, metadata: Optional[Dict] = None):
        """Record an event."""
        self.events.append({
            "event_type": event_type,
            "detail": detail,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
    
    def analyze(self, window_minutes: int = 60) -> List[SemanticPattern]:
        """Analyze recent events for temporal patterns."""
        patterns = []
        
        if len(self.events) < 5:
            return patterns
        
        now = datetime.now()
        recent = [
            e for e in self.events
            if (now - datetime.fromisoformat(e["timestamp"])).total_seconds() < window_minutes * 60
        ]
        
        if len(recent) < 5:
            return patterns
        
        # Check for failure streaks
        failure_streak = 0
        max_streak = 0
        for e in recent:
            if not e["success"]:
                failure_streak += 1
                max_streak = max(max_streak, failure_streak)
            else:
                failure_streak = 0
        
        if max_streak >= 3:
            patterns.append(SemanticPattern(
                pattern_type=PatternType.TEMPORAL,
                name="failure_streak",
                description=f"Detected {max_streak} consecutive failures in last {window_minutes} min",
                severity=PatternSeverity.WARNING,
                confidence=min(max_streak / 5.0, 1.0),
                occurrences=max_streak,
                examples=[e["detail"][:50] for e in recent if not e["success"]][:5],
                suggested_rule="After 3+ failures, pause and try a different approach",
                metadata={"window_minutes": window_minutes}
            ))
        
        # Check for repeated identical actions
        action_counts = Counter(e["event_type"] for e in recent)
        for action, count in action_counts.most_common(3):
            if count >= 5:
                patterns.append(SemanticPattern(
                    pattern_type=PatternType.TEMPORAL,
                    name="repeated_action",
                    description=f"Action '{action}' repeated {count} times in {window_minutes} min",
                    severity=PatternSeverity.INFO,
                    confidence=min(count / 10.0, 1.0),
                    occurrences=count,
                    examples=[e["detail"][:50] for e in recent if e["event_type"] == action][:5],
                    suggested_rule="If action isn't making progress, try alternative approach",
                    metadata={"action": action, "window_minutes": window_minutes}
                ))
        
        return patterns


class SemanticAnalyzer:
    """
    Combined semantic analysis engine.
    
    Combines:
    - Code pattern analysis
    - Metric correlation
    - Temporal patterns
    """
    
    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path(".ouroboros/semantic")
        self.code_analyzer = CodeAnalyzer()
        self.metric_analyzer = MetricCorrelationAnalyzer()
        self.temporal_analyzer = TemporalPatternAnalyzer()
        
        self._load_state()
    
    def _load_state(self):
        """Load saved state."""
        if not self.state_dir.exists():
            return
        
        self.metric_analyzer.load(self.state_dir / "metric_history.json")
        
        events_path = self.state_dir / "events.json"
        if events_path.exists():
            with open(events_path) as f:
                self.temporal_analyzer.events = json.load(f)
    
    def _save_state(self):
        """Save state."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.metric_analyzer.save(self.state_dir / "metric_history.json")
        
        with open(self.state_dir / "events.json", "w") as f:
            json.dump(self.temporal_analyzer.events[-1000:], f, indent=2)  # Keep last 1000
    
    def analyze_code(self, code: str, filename: str = "unknown") -> List[SemanticPattern]:
        """Analyze code for patterns."""
        return self.code_analyzer.analyze(code, filename)
    
    def record_action(self, action_type: str, action_detail: str,
                      metric_before: float, metric_after: float,
                      event_success: bool = True):
        """Record an action and its outcome."""
        self.metric_analyzer.add_entry(action_type, action_detail, metric_before, metric_after)
        self.temporal_analyzer.add_event(action_type, action_detail, event_success)
        self._save_state()
    
    def analyze_all(self, code: Optional[str] = None, 
                    filename: str = "unknown") -> List[SemanticPattern]:
        """
        Run all analyses and return combined patterns.
        
        Patterns are sorted by severity and confidence.
        """
        patterns = []
        
        # Code patterns
        if code:
            patterns.extend(self.code_analyzer.analyze(code, filename))
        
        # Metric correlations
        patterns.extend(self.metric_analyzer.analyze())
        
        # Temporal patterns
        patterns.extend(self.temporal_analyzer.analyze())
        
        # Sort by severity (critical first) then confidence
        severity_order = {
            PatternSeverity.CRITICAL: 0,
            PatternSeverity.ERROR: 1,
            PatternSeverity.WARNING: 2,
            PatternSeverity.INFO: 3
        }
        
        patterns.sort(key=lambda p: (severity_order[p.severity], -p.confidence))
        
        return patterns
    
    def get_rules(self, patterns: Optional[List[SemanticPattern]] = None) -> List[str]:
        """Extract suggested rules from patterns."""
        if patterns is None:
            patterns = self.analyze_all()
        
        rules = []
        seen = set()
        
        for pattern in patterns:
            if pattern.suggested_rule and pattern.suggested_rule not in seen:
                rules.append(pattern.suggested_rule)
                seen.add(pattern.suggested_rule)
        
        return rules
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of detected patterns."""
        patterns = self.analyze_all()
        
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        
        for p in patterns:
            by_type[p.pattern_type.value] = by_type.get(p.pattern_type.value, 0) + 1
            by_severity[p.severity.value] = by_severity.get(p.severity.value, 0) + 1
        
        return {
            "total_patterns": len(patterns),
            "by_type": by_type,
            "by_severity": by_severity,
            "metric_history_size": len(self.metric_analyzer.history),
            "event_history_size": len(self.temporal_analyzer.events),
            "top_rules": self.get_rules(patterns)[:10]
        }


# === CLI Interface ===

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Semantic Pattern Analyzer")
    parser.add_argument("command", choices=["analyze", "rules", "summary"])
    parser.add_argument("--file", help="File to analyze")
    parser.add_argument("--code", help="Code string to analyze")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    analyzer = SemanticAnalyzer()
    
    if args.command == "analyze":
        code = None
        filename = "unknown"
        
        if args.file:
            with open(args.file) as f:
                code = f.read()
            filename = args.file
        elif args.code:
            code = args.code
        
        if code:
            patterns = analyzer.analyze_all(code, filename)
            if args.json:
                print(json.dumps([p.to_dict() for p in patterns], indent=2))
            else:
                for p in patterns:
                    icon = {"critical": "🔥", "error": "❌", "warning": "⚠️", "info": "ℹ️"}[p.severity.value]
                    print(f"{icon} [{p.pattern_type.value}] {p.name}: {p.description}")
                    if p.suggested_rule:
                        print(f"   → {p.suggested_rule}")
        else:
            print("Error: --file or --code required")
    
    elif args.command == "rules":
        rules = analyzer.get_rules()
        for i, rule in enumerate(rules, 1):
            print(f"{i}. {rule}")
    
    elif args.command == "summary":
        summary = analyzer.get_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Total Patterns: {summary['total_patterns']}")
            print(f"Metric History: {summary['metric_history_size']} entries")
            print(f"Event History: {summary['event_history_size']} entries")
            print("\nBy Type:")
            for t, c in summary["by_type"].items():
                print(f"  {t}: {c}")
            print("\nBy Severity:")
            for s, c in summary["by_severity"].items():
                print(f"  {s}: {c}")
            print("\nTop Rules:")
            for i, rule in enumerate(summary["top_rules"], 1):
                print(f"  {i}. {rule}")
