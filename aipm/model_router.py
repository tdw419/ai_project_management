"""
Model Router -- smart provider selection for AIPM agent runs.

Instead of a hardcoded "attempt 1-2 = local, attempt 3+ = cloud" rule,
this combines two signals:

1. COMPLEXITY SCORING (heuristic, free, instant)
   - Analyzes issue title/body for keywords that signal hard or easy tasks
   - Checks project history for known-hard patterns
   - Looks at acceptance criteria specificity

2. OUTCOME HISTORY (learns over time, no extra API calls)
   - Tracks success rate per project per provider
   - If local is working well for a project, keep using it
   - If local keeps failing, escalate to cloud sooner
   - Per-issue escalation: if same issue failed on local, try cloud next

3. PROVIDER HEALTH / CIRCUIT BREAKER (time-windowed, prevents waste)
   - Tracks timeout/error outcomes per provider in a rolling window
   - If cloud has timed out 3+ times in the last 30 minutes, skip it
   - Prevents sending 200K-token requests to a dead endpoint

The router returns a model string like "qwen3.5-tools" or "zai/glm-5.1"
that gets passed to `hermes chat -m <model>`.

Schema: provider column added to prompt_log to track which provider was used.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Tuple
from pathlib import Path


class Provider(Enum):
    LOCAL = "local"
    CLOUD = "cloud"


# ── Model strings passed to `hermes chat -m` ──────────────────────────

LOCAL_MODEL = "qwen3.5-tools"
CLOUD_MODEL = "glm-5.1"


# ── Complexity Scoring ────────────────────────────────────────────────

# Keywords that signal a task is likely HARD for a coding agent.
# These involve domain expertise, multi-system coordination, or
# architectural reasoning that weaker models struggle with.
HARD_KEYWORDS = [
    # GPU / shaders
    "shader", "wgsl", "glsl", "hlsl", "vulkan", "cuda", "gpu",
    # Systems programming
    "compiler", "interpreter", "opcode", "bytecode", "vm", "virtual machine",
    "risc-v", "riscv", "assembler", "disassembler",
    # Architecture
    "refactor", "architecture", "redesign", "rewrite", "migration",
    "multi-thread", "concurrent", "async runtime", "event loop",
    # Complex domains
    "parser", "tokenizer", "lexer", "ast", "grammar",
    "protocol", "serialization", "codec", "encryption",
    "physics", "collision", "raytracing", "rendering pipeline",
    # Cross-cutting
    "integration test", "e2e", "end-to-end", "benchmark",
    "performance optimization", "memory leak", "profiling",
]

# Keywords that signal a task is likely EASY -- well-scoped, mechanical.
EASY_KEYWORDS = [
    "typo", "rename", "documentation", "comment", "readme",
    "fix lint", "whitespace", "formatting", "unused import",
    "log message", "error message", "constant",
    "add test", "update test", "test case",
    "stub", "placeholder", "todo", "fixme",
    "gitignore", "license", "config",
]

# Issue body patterns that indicate good scoping (easier for agents).
WELL_SCOPED_PATTERNS = [
    "```bash",     # Has exact commands to verify
    "acceptance criteria",
    "do not modify",
    "file to create",
    "file to modify",
    "exact path",
]


def score_complexity(
    issue_title: str,
    issue_body: str,
    project_language: str = "",
    files_to_modify: int = 0,
) -> float:
    """Estimate task complexity on a scale roughly -5 (easy) to +5 (hard).

    No model calls -- pure heuristic based on keywords and structure.
    """
    text = (issue_title + " " + issue_body).lower()
    score = 0.0

    # Keyword signals
    for kw in HARD_KEYWORDS:
        if kw in text:
            score += 1.5

    for kw in EASY_KEYWORDS:
        if kw in text:
            score -= 1.5

    # Well-scoped issues are easier regardless of domain
    for pattern in WELL_SCOPED_PATTERNS:
        if pattern in text:
            score -= 1.0

    # Many files = harder (more coordination needed)
    if files_to_modify > 3:
        score += 2.0
    elif files_to_modify > 1:
        score += 0.5

    # Some languages are harder for agents
    hard_langs = {"rust", "go", "zig", "c", "cpp", "wgsl", "glsl"}
    if project_language.lower() in hard_langs:
        score += 0.5

    return score


def score_complexity_from_context(
    task_context,  # TaskContext from openspec_adapter
    project_language: str = "",
) -> float:
    """Score complexity using structured OpenSpec signals instead of raw keywords.

    This is more accurate than score_complexity() because it uses real
    metadata (file counts, dependency depth, design docs) rather than
    guessing from text.

    Args:
        task_context: TaskContext from openspec_adapter.extract_task_context()
        project_language: project language for lang-specific scoring

    Returns:
        float score -- higher = harder. Range roughly -3 to +8.
    """
    score = 0.0

    # ── File count: the strongest signal ──────────────────────────────
    # More files = more coordination, more integration points
    fc = task_context.file_count
    if fc >= 8:
        score += 4.0
    elif fc >= 5:
        score += 3.0
    elif fc >= 3:
        score += 1.5
    elif fc >= 2:
        score += 0.5
    # 0-1 files = no bonus (easy by default)

    # ── Step count: more steps = more complex task ────────────────────
    sc = task_context.step_count
    if sc >= 10:
        score += 2.0
    elif sc >= 6:
        score += 1.5
    elif sc >= 3:
        score += 0.5

    # ── Design doc present: thought-through tasks are EASIER ──────────
    # because the agent has a clear plan to follow
    if task_context.has_design_doc:
        score -= 1.0

    # ── Requirements: formal specs make tasks EASIER ─────────────────
    if task_context.has_requirements:
        score -= 1.0

    # ── Component count: more components = harder integration ────────
    cc = task_context.component_count
    if cc >= 4:
        score += 2.0
    elif cc >= 2:
        score += 1.0

    # ── Cross-component: task touches multiple systems ───────────────
    if task_context.cross_component:
        score += 1.5

    # ── Dependency depth: deep chains mean cumulative risk ───────────
    dd = task_context.dependency_depth
    if dd >= 3:
        score += 2.0
    elif dd >= 2:
        score += 1.0
    elif dd >= 1:
        score += 0.5

    # ── Success criteria: many criteria = more to verify = harder ────
    scc = task_context.success_criteria_count
    if scc >= 5:
        score += 1.0
    elif scc >= 3:
        score += 0.5

    # ── Risks: identified risks signal complexity ────────────────────
    rc = task_context.proposal_risk_count
    if rc >= 4:
        score += 1.0
    elif rc >= 2:
        score += 0.5

    # ── Change progress: tasks deep in a change are riskier ──────────
    # (earlier failures may have left debt)
    if task_context.change_completed_pct > 75:
        score += 0.5  # late-stage tasks in a change = trickier

    # ── Keyword fallback on task description ─────────────────────────
    # Still use keyword matching on the description as a tiebreaker
    text = (task_context.task_description + " " + task_context.change_title).lower()
    for kw in HARD_KEYWORDS:
        if kw in text:
            score += 0.8  # reduced weight vs raw score_complexity
    for kw in EASY_KEYWORDS:
        if kw in text:
            score -= 0.8

    # ── Language bonus ───────────────────────────────────────────────
    hard_langs = {"rust", "go", "zig", "c", "cpp", "wgsl", "glsl"}
    if project_language.lower() in hard_langs:
        score += 0.5

    return score


# ── Outcome History ───────────────────────────────────────────────────

def get_provider_stats(
    db_path: str,
    project: str,
    lookback: int = 50,
) -> dict:
    """Get success rates per provider for a project from prompt_log.

    Returns: {"local": {"total": N, "success": N, "rate": float},
              "cloud": {"total": N, "success": N, "rate": float}}
    """
    stats = {
        "local": {"total": 0, "success": 0, "rate": 0.0},
        "cloud": {"total": 0, "success": 0, "rate": 0.0},
    }

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT provider, outcome_status
                FROM prompt_log
                WHERE project = ? AND provider IS NOT NULL AND provider != ''
                ORDER BY timestamp DESC LIMIT ?
            """, (project, lookback)).fetchall()

            for row in rows:
                p = row["provider"]
                if p not in stats:
                    continue
                stats[p]["total"] += 1
                if row["outcome_status"] == "success":
                    stats[p]["success"] += 1

            for p in stats:
                if stats[p]["total"] > 0:
                    stats[p]["rate"] = stats[p]["success"] / stats[p]["total"]
    except sqlite3.OperationalError:
        # provider column doesn't exist yet -- return defaults
        pass

    return stats


def get_issue_provider_history(
    db_path: str,
    project: str,
    issue_number: int,
) -> List[Tuple[str, str]]:
    """Get (provider, outcome) for each attempt on a specific issue.

    Used to decide if we should switch providers for a retry.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT provider, outcome_status
                FROM prompt_log
                WHERE project = ? AND issue_number = ? AND provider IS NOT NULL
                ORDER BY attempt_number ASC
            """, (project, issue_number)).fetchall()

            return [(r["provider"], r["outcome_status"]) for r in rows]
    except sqlite3.OperationalError:
        return []


# ── Main Router ───────────────────────────────────────────────────────

@dataclass
class ProviderHealth:
    """Time-windowed health status for one provider."""
    is_healthy: bool
    recent_failures: int    # timeout/error count in lookback window
    last_failure_at: str    # ISO timestamp of most recent failure, or ""


def get_provider_health(
    db_path: str,
    provider: str,
    lookback_minutes: int = 30,
    min_failures: int = 3,
) -> ProviderHealth:
    """Check if a provider is healthy based on recent timeout/error rate.

    A provider is considered unhealthy if it has >= min_failures outcomes
    with status 'timeout' or 'error' in the last lookback_minutes window.
    This is a circuit breaker: once tripped, the router avoids the provider
    until it recovers (i.e., enough time passes with no new failures).

    Args:
        db_path: Path to the prompt_log SQLite database.
        provider: "local" or "cloud".
        lookback_minutes: How far back to look for failures (default 30m).
        min_failures: Failures needed to declare a provider unhealthy (default 3).

    Returns:
        ProviderHealth with is_healthy=False if circuit should be open.
    """
    cutoff = (datetime.now() - timedelta(minutes=lookback_minutes)).isoformat()

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS failures, MAX(timestamp) AS last_failure
                FROM prompt_log
                WHERE provider = ?
                  AND timestamp > ?
                  AND outcome_status IN ('timeout', 'error')
            """, (provider, cutoff)).fetchone()

            failures = row[0] if row else 0
            last_failure_at = row[1] or ""

            return ProviderHealth(
                is_healthy=failures < min_failures,
                recent_failures=failures,
                last_failure_at=last_failure_at,
            )
    except sqlite3.OperationalError:
        # DB doesn't exist yet or missing columns -- assume healthy
        return ProviderHealth(is_healthy=True, recent_failures=0, last_failure_at="")


@dataclass
class RoutingDecision:
    """Why we chose this provider."""
    model: str           # Model string for `hermes chat -m`
    provider: str        # "local" or "cloud" (for logging to prompt_log)
    reason: str          # Human-readable explanation
    complexity_score: float
    local_success_rate: float
    cloud_success_rate: float


def select_model(
    db_path: str,
    project: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    attempt_number: int,
    project_language: str = "",
    files_to_modify: int = 0,
    force_provider: Optional[str] = None,
) -> RoutingDecision:
    """Select the best model for this run.

    Decision logic:
    1. If force_provider is set, use that (manual override)
    2. If attempt_number >= 3, always escalate to cloud (hard failures need stronger model)
    3. If same issue already failed on local, try cloud next
    4. Score complexity -- hard tasks go straight to cloud
    5. Check project history -- if local is failing, prefer cloud
    6. Default to local (cheapest, fastest)
    """
    # --- Override ---
    if force_provider:
        model = LOCAL_MODEL if force_provider == "local" else CLOUD_MODEL
        return RoutingDecision(
            model=model,
            provider=force_provider,
            reason=f"Manual override: {force_provider}",
            complexity_score=0.0,
            local_success_rate=0.0,
            cloud_success_rate=0.0,
        )

    # --- Complexity scoring ---
    complexity = score_complexity(
        issue_title, issue_body, project_language, files_to_modify
    )

    # --- Provider history ---
    provider_stats = get_provider_stats(db_path, project)
    local_rate = provider_stats["local"]["rate"]
    cloud_rate = provider_stats["cloud"]["rate"]
    local_total = provider_stats["local"]["total"]

    # --- Provider health (circuit breaker) ---
    cloud_health = get_provider_health(db_path, "cloud")
    local_health = get_provider_health(db_path, "local")

    # --- Issue-level history ---
    issue_history = get_issue_provider_history(db_path, project, issue_number)
    last_provider = issue_history[-1][0] if issue_history else None
    local_failures_on_issue = sum(
        1 for p, o in issue_history
        if p == "local" and o != "success"
    )

    # === Decision tree ===

    # Rule 1: After 3+ attempts, always escalate to cloud.
    # The local model has had its chance and failed.
    if attempt_number >= 3:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Attempt {attempt_number} >= 3 (would escalate) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- staying on local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Attempt {attempt_number} >= 3, escalating to cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 2: If issue already failed 2+ times on local, try cloud.
    # Don't keep banging the same wall with the same hammer.
    if local_failures_on_issue >= 2:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Issue failed {local_failures_on_issue}x on local (would switch) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- retrying local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Issue failed {local_failures_on_issue}x on local, switching to cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 3: High complexity tasks go straight to cloud.
    # Threshold: score > 3.0 means multiple hard keywords or many files.
    if complexity > 3.0:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"High complexity ({complexity:.1f}) (would use cloud) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- using local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"High complexity ({complexity:.1f}), routing to cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 4: If project's local success rate is below 15%, prefer cloud.
    # 2 consecutive failures with 0% success is enough signal to switch.
    if local_total >= 2 and local_rate < 0.15:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Local rate {local_rate:.0%} < 15% (would use cloud) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- using local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Local success rate {local_rate:.0%} < 15% for {project} ({local_total} attempts), using cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 5: If the last attempt on this issue was on local and failed,
    # alternate to cloud for the retry. Gives the stronger model a shot.
    if last_provider == "local" and issue_history and issue_history[-1][1] != "success":
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Last attempt local ({issue_history[-1][1]}) (would retry on cloud) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- retrying local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Last attempt was local ({issue_history[-1][1]}), retrying on cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 6: Default to local. It's free, fast, and handles most tasks.
    # If local is also unhealthy, use cloud as fallback.
    if not local_health.is_healthy and cloud_health.is_healthy:
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Default would be local but local circuit open ({local_health.recent_failures} failures/30m) -- using cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )
    return RoutingDecision(
        model=LOCAL_MODEL,
        provider="local",
        reason=f"Default local (complexity={complexity:.1f}, local_rate={local_rate:.0%})",
        complexity_score=complexity,
        local_success_rate=local_rate,
        cloud_success_rate=cloud_rate,
    )


def select_model_from_context(
    db_path: str,
    project: str,
    issue_number: int,
    task_context,  # TaskContext from openspec_adapter
    attempt_number: int,
    project_language: str = "",
    force_provider: Optional[str] = None,
) -> RoutingDecision:
    """Select model using structured OpenSpec context instead of raw strings.

    Same decision tree as select_model() but uses score_complexity_from_context()
    for more accurate complexity assessment. Also adds spec-aware rules:

    - Rule 7: Tasks with design docs AND requirements can start on local
      even at medium complexity (they're well-specified)
    - Rule 8: Tasks deep in dependency chains get a complexity bump

    Drop-in replacement for select_model() in the spec-driven path.
    """
    # --- Override ---
    if force_provider:
        model = LOCAL_MODEL if force_provider == "local" else CLOUD_MODEL
        return RoutingDecision(
            model=model,
            provider=force_provider,
            reason=f"Manual override: {force_provider}",
            complexity_score=0.0,
            local_success_rate=0.0,
            cloud_success_rate=0.0,
        )

    # --- Context-aware complexity scoring ---
    complexity = score_complexity_from_context(task_context, project_language)

    # --- Provider history ---
    provider_stats = get_provider_stats(db_path, project)
    local_rate = provider_stats["local"]["rate"]
    cloud_rate = provider_stats["cloud"]["rate"]
    local_total = provider_stats["local"]["total"]

    # --- Provider health (circuit breaker) ---
    cloud_health = get_provider_health(db_path, "cloud")
    local_health = get_provider_health(db_path, "local")

    # --- Issue-level history ---
    issue_history = get_issue_provider_history(db_path, project, issue_number)
    last_provider = issue_history[-1][0] if issue_history else None
    local_failures_on_issue = sum(
        1 for p, o in issue_history
        if p == "local" and o != "success"
    )

    # === Decision tree (same structure, context-aware thresholds) ===

    # Rule 1: After 3+ attempts, always escalate to cloud.
    if attempt_number >= 3:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Attempt {attempt_number} >= 3 (would escalate) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- staying on local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Attempt {attempt_number} >= 3, escalating to cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 2: If issue already failed 2+ times on local, try cloud.
    if local_failures_on_issue >= 2:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Issue failed {local_failures_on_issue}x on local (would switch) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- retrying local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Issue failed {local_failures_on_issue}x on local, switching to cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 3: High complexity tasks go straight to cloud.
    # Context-aware threshold: slightly higher than raw because context
    # scoring is more granular. A context score of 4.0 is genuinely hard.
    if complexity > 4.0:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"High complexity ({complexity:.1f}) (would use cloud) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- using local [{task_context.summary()}]",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"High complexity ({complexity:.1f}), routing to cloud [{task_context.summary()}]",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 4: If project's local success rate is below 15%, prefer cloud.
    if local_total >= 2 and local_rate < 0.15:
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Local rate {local_rate:.0%} < 15% (would use cloud) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- using local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Local success rate {local_rate:.0%} < 15% for {project} ({local_total} attempts), using cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 5: If last attempt was local and failed, retry on cloud.
    if last_provider == "local" and issue_history and issue_history[-1][1] != "success":
        if not cloud_health.is_healthy:
            return RoutingDecision(
                model=LOCAL_MODEL,
                provider="local",
                reason=f"Last attempt local ({issue_history[-1][1]}) (would retry on cloud) but cloud circuit open ({cloud_health.recent_failures} failures/30m) -- retrying local",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Last attempt was local ({issue_history[-1][1]}), retrying on cloud",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 6 (spec-aware): Well-specified tasks with design docs
    # AND requirements can go local even at medium complexity (3.0-4.0).
    if (
        task_context.has_design_doc
        and task_context.has_requirements
        and complexity <= 4.0
    ):
        if not local_health.is_healthy and cloud_health.is_healthy:
            return RoutingDecision(
                model=CLOUD_MODEL,
                provider="cloud",
                reason=f"Well-specified task but local circuit open ({local_health.recent_failures} failures/30m) -- using cloud [{task_context.summary()}]",
                complexity_score=complexity,
                local_success_rate=local_rate,
                cloud_success_rate=cloud_rate,
            )
        return RoutingDecision(
            model=LOCAL_MODEL,
            provider="local",
            reason=f"Well-specified task [{task_context.summary()}] -> local (complexity={complexity:.1f})",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )

    # Rule 7: Default to local. Fall back to cloud if local circuit is open.
    if not local_health.is_healthy and cloud_health.is_healthy:
        return RoutingDecision(
            model=CLOUD_MODEL,
            provider="cloud",
            reason=f"Default would be local but local circuit open ({local_health.recent_failures} failures/30m) -- using cloud [{task_context.summary()}]",
            complexity_score=complexity,
            local_success_rate=local_rate,
            cloud_success_rate=cloud_rate,
        )
    return RoutingDecision(
        model=LOCAL_MODEL,
        provider="local",
        reason=f"Default local (complexity={complexity:.1f}, local_rate={local_rate:.0%}) [{task_context.summary()}]",
        complexity_score=complexity,
        local_success_rate=local_rate,
        cloud_success_rate=cloud_rate,
    )
