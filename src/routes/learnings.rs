use axum::{extract::{Path, State}, response::Json};
use serde::{Deserialize, Serialize};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};

// -- P11-A: Company Learnings --

/// Per-strategy success rate breakdown.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategyStats {
    pub strategy: String,
    pub total: i64,
    pub successes: i64,
    pub success_rate: f64,
    pub avg_duration_ms: f64,
    pub avg_test_delta: f64,
}

/// A module difficulty entry.
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct ModuleDifficulty {
    pub id: String,
    pub company_id: String,
    pub file_path: String,
    pub total_attempts: i64,
    pub failures: i64,
    pub successes: i64,
    pub avg_duration_ms: f64,
    pub last_attempt_at: Option<String>,
    pub difficulty: String,
    pub created_at: String,
    pub updated_at: String,
}

/// An actionable recommendation generated from learnings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Recommendation {
    pub kind: String,      // "strategy", "module", "trend", "general"
    pub severity: String,  // "info", "warning", "critical"
    pub message: String,
}

/// The full learnings response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LearningsResponse {
    pub company_id: String,
    pub overall_success_rate: f64,
    pub total_outcomes: i64,
    pub total_successes: i64,
    pub total_failures: i64,
    pub net_test_delta: i64,
    pub avg_duration_ms: f64,
    pub trend: String,              // "improving", "declining", "stable"
    pub by_strategy: Vec<StrategyStats>,
    pub modules: Vec<ModuleDifficulty>,
    pub recommendations: Vec<Recommendation>,
}

/// GET /api/companies/{cid}/learnings
///
/// Aggregates outcome history into actionable learnings:
/// - Overall success rate
/// - Per-strategy breakdown (scout/surgeon/builder/fixer/refactor)
/// - Net test delta across all completed issues
/// - Average issue duration (started_at -> completed_at)
/// - Recent trend (compare last 10 vs previous 10)
/// - Module difficulty (from module_difficulty table)
/// - Actionable recommendations
pub async fn get_learnings(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<LearningsResponse>> {
    // Verify company exists
    let _company = query_as::<_, crate::db::models::Company>(
        "SELECT * FROM companies WHERE id = ?"
    )
        .bind(&cid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Company {} not found", cid)))?;

    // -- Overall success rate --
    let total_outcomes: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM issue_outcomes io
         JOIN issues i ON io.issue_id = i.id
         WHERE i.company_id = ?"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    let total_successes: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM issue_outcomes io
         JOIN issues i ON io.issue_id = i.id
         WHERE i.company_id = ? AND io.success = 1"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    let total_failures = total_outcomes.0 - total_successes.0;
    let overall_success_rate = if total_outcomes.0 > 0 {
        (total_successes.0 as f64 / total_outcomes.0 as f64 * 100.0 * 10.0).round() / 10.0
    } else {
        0.0
    };

    // -- Net test delta --
    let net_test_delta: (i64,) = sqlx::query_as(
        "SELECT COALESCE(SUM(io.tests_after - io.tests_before), 0)
         FROM issue_outcomes io
         JOIN issues i ON io.issue_id = i.id
         WHERE i.company_id = ? AND io.success = 1"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    // -- Average duration --
    let avg_duration: (f64,) = sqlx::query_as(
        "SELECT COALESCE(AVG(
            (julianday(i.completed_at) - julianday(i.started_at)) * 86400000
         ), 0.0)
         FROM issues i
         WHERE i.company_id = ? AND i.started_at IS NOT NULL AND i.completed_at IS NOT NULL
         AND i.status IN ('done', 'cancelled')"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0.0,));

    // -- Per-strategy breakdown --
    let strategies = crate::db::models::STRATEGIES;
    let mut by_strategy = Vec::new();
    for &s in strategies {
        let (total,): (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM issue_outcomes io
             JOIN issues i ON io.issue_id = i.id
             WHERE i.company_id = ? AND i.strategy = ?"
        )
            .bind(&cid)
            .bind(s)
            .fetch_one(&state.pool)
            .await
            .unwrap_or((0,));

        if total == 0 {
            continue;
        }

        let (successes,): (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM issue_outcomes io
             JOIN issues i ON io.issue_id = i.id
             WHERE i.company_id = ? AND i.strategy = ? AND io.success = 1"
        )
            .bind(&cid)
            .bind(s)
            .fetch_one(&state.pool)
            .await
            .unwrap_or((0,));

        let (avg_dur,): (f64,) = sqlx::query_as(
            "SELECT COALESCE(AVG(io.duration_ms), 0.0) FROM issue_outcomes io
             JOIN issues i ON io.issue_id = i.id
             WHERE i.company_id = ? AND i.strategy = ?"
        )
            .bind(&cid)
            .bind(s)
            .fetch_one(&state.pool)
            .await
            .unwrap_or((0.0,));

        let (avg_delta,): (f64,) = sqlx::query_as(
            "SELECT COALESCE(AVG(CAST(io.tests_after - io.tests_before AS REAL)), 0.0)
             FROM issue_outcomes io
             JOIN issues i ON io.issue_id = i.id
             WHERE i.company_id = ? AND i.strategy = ?"
        )
            .bind(&cid)
            .bind(s)
            .fetch_one(&state.pool)
            .await
            .unwrap_or((0.0,));

        by_strategy.push(StrategyStats {
            strategy: s.to_string(),
            total,
            successes,
            success_rate: (successes as f64 / total as f64 * 100.0 * 10.0).round() / 10.0,
            avg_duration_ms: (avg_dur * 10.0).round() / 10.0,
            avg_test_delta: (avg_delta * 10.0).round() / 10.0,
        });
    }

    // -- Trend: compare last 10 outcomes vs previous 10 --
    let trend = compute_trend(&state, &cid).await;

    // -- Module difficulty --
    let modules = query_as::<_, ModuleDifficulty>(
        "SELECT * FROM module_difficulty WHERE company_id = ? ORDER BY total_attempts DESC"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    // -- Recommendations --
    let recommendations = generate_recommendations(
        overall_success_rate,
        total_outcomes.0,
        &by_strategy,
        &modules,
        &trend,
    );

    Ok(Json(LearningsResponse {
        company_id: cid,
        overall_success_rate,
        total_outcomes: total_outcomes.0,
        total_successes: total_successes.0,
        total_failures,
        net_test_delta: net_test_delta.0,
        avg_duration_ms: (avg_duration.0 * 10.0).round() / 10.0,
        trend,
        by_strategy,
        modules,
        recommendations,
    }))
}

/// P11-C: Get relevant learnings for a dispatch response.
/// Returns module warnings and strategy hints relevant to the specific issue being dispatched.
pub async fn get_learnings_for_dispatch(
    state: &SharedState,
    company_id: &str,
    issue: &crate::db::models::Issue,
) -> serde_json::Value {
    // Gather relevant module warnings for files this issue might touch
    // (We don't know the files yet, so check if the description mentions known hard modules)
    let hard_modules: Vec<ModuleDifficulty> = query_as::<_, ModuleDifficulty>(
        "SELECT * FROM module_difficulty WHERE company_id = ? AND difficulty = 'hard' ORDER BY failures DESC LIMIT 5"
    )
        .bind(company_id)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    // Check if the issue description references any hard modules
    let desc_text = issue.description.as_deref().unwrap_or("").to_lowercase();
    let title_text = issue.title.to_lowercase();
    let combined = format!("{} {}", title_text, desc_text);

    let mut relevant_warnings: Vec<serde_json::Value> = Vec::new();
    for m in &hard_modules {
        // Extract filename from path for matching
        let file_name = m.file_path.split('/').last().unwrap_or(&m.file_path).to_lowercase();
        if combined.contains(&file_name) || combined.contains(&m.file_path.to_lowercase()) {
            relevant_warnings.push(serde_json::json!({
                "file": m.file_path,
                "failures": m.failures,
                "attempts": m.total_attempts,
                "message": format!("Module {} has {} failures in {} attempts -- consider smaller steps",
                    m.file_path, m.failures, m.total_attempts),
            }));
        }
    }

    // Get overall success rate for context
    let (total, successes): (i64, i64) = sqlx::query_as(
        "SELECT COUNT(*), COALESCE(SUM(CASE WHEN io.success = 1 THEN 1 ELSE 0 END), 0)
         FROM issue_outcomes io
         JOIN issues i ON io.issue_id = i.id
         WHERE i.company_id = ?"
    )
        .bind(company_id)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0, 0));

    let success_rate = if total > 0 {
        (successes as f64 / total as f64 * 100.0 * 10.0).round() / 10.0
    } else {
        0.0
    };

    // Get avg duration for similar strategy issues
    let avg_duration: f64 = if let Some(ref strategy) = issue.strategy {
        let (d,): (f64,) = sqlx::query_as(
            "SELECT COALESCE(AVG(io.duration_ms), 0.0) FROM issue_outcomes io
             JOIN issues i ON io.issue_id = i.id
             WHERE i.company_id = ? AND i.strategy = ?"
        )
            .bind(company_id)
            .bind(strategy)
            .fetch_one(&state.pool)
            .await
            .unwrap_or((0.0,));
        (d * 10.0).round() / 10.0
    } else {
        0.0
    };

    serde_json::json!({
        "overallSuccessRate": success_rate,
        "totalOutcomes": total,
        "avgDurationMs": avg_duration,
        "moduleWarnings": relevant_warnings,
    })
}

/// P11-E: Recompute module difficulty from all outcomes.
/// Called after every new outcome is recorded.
pub async fn recompute_module_difficulty(state: &SharedState, company_id: &str) {
    // Get all outcomes for this company with their file lists
    let outcomes: Vec<(String, bool, i64, String)> = sqlx::query_as(
        "SELECT io.files_changed, io.success, io.duration_ms, io.created_at
         FROM issue_outcomes io
         JOIN issues i ON io.issue_id = i.id
         WHERE i.company_id = ?
         ORDER BY io.created_at ASC"
    )
        .bind(company_id)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    // Aggregate per file
    use std::collections::HashMap;
    let mut file_stats: HashMap<String, (i64, i64, i64, f64, String)> = HashMap::new();
    // (total, failures, successes, sum_duration, last_attempt_at)

    for (files_json, success, duration_ms, created_at) in &outcomes {
        let files: Vec<String> = serde_json::from_str(files_json).unwrap_or_default();
        for file in files {
            let entry = file_stats.entry(file).or_insert((0, 0, 0, 0.0, String::new()));
            entry.0 += 1;
            if *success {
                entry.2 += 1;
            } else {
                entry.1 += 1;
            }
            entry.3 += *duration_ms as f64;
            entry.4 = created_at.clone();
        }
    }

    // Upsert into module_difficulty
    for (file_path, (total, failures, successes, sum_dur, last_at)) in &file_stats {
        let avg_dur = if *total > 0 { sum_dur / *total as f64 } else { 0.0 };
        let failure_rate = if *total > 0 { *failures as f64 / *total as f64 } else { 0.0 };

        let difficulty = if *total < 2 {
            "unknown"
        } else if failure_rate >= 0.6 {
            "hard"
        } else if failure_rate >= 0.3 {
            "medium"
        } else {
            "easy"
        };

        let id = Uuid::new_v4().to_string();

        // Try update first, insert if not exists
        let updated = sqlx::query(
            "UPDATE module_difficulty SET total_attempts = ?, failures = ?, successes = ?,
             avg_duration_ms = ?, last_attempt_at = ?, difficulty = ?,
             updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
             WHERE company_id = ? AND file_path = ?"
        )
            .bind(total)
            .bind(failures)
            .bind(successes)
            .bind(avg_dur)
            .bind(last_at)
            .bind(difficulty)
            .bind(company_id)
            .bind(&file_path)
            .execute(&state.pool)
            .await
            .map(|r| r.rows_affected())
            .unwrap_or(0);

        if updated == 0 {
            let _ = sqlx::query(
                "INSERT INTO module_difficulty (id, company_id, file_path, total_attempts,
                 failures, successes, avg_duration_ms, last_attempt_at, difficulty)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
                .bind(&id)
                .bind(company_id)
                .bind(&file_path)
                .bind(total)
                .bind(failures)
                .bind(successes)
                .bind(avg_dur)
                .bind(last_at)
                .bind(difficulty)
                .execute(&state.pool)
                .await;
        }
    }

    tracing::info!(
        company_id = %company_id,
        files_tracked = file_stats.len(),
        "Recomputed module difficulty"
    );
}

/// P11-B: GET /api/companies/{cid}/learnings/modules
/// Return just the module difficulty data.
pub async fn get_module_difficulty(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<ModuleDifficulty>>> {
    let modules = query_as::<_, ModuleDifficulty>(
        "SELECT * FROM module_difficulty WHERE company_id = ? ORDER BY
         CASE difficulty WHEN 'hard' THEN 1 WHEN 'medium' THEN 2 WHEN 'easy' THEN 3 ELSE 4 END,
         total_attempts DESC"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();
    Ok(Json(modules))
}

/// P11-E: POST /api/companies/{cid}/learnings/recompute
/// Manual trigger to recompute learnings from all outcome history.
pub async fn trigger_recompute(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    // Verify company exists
    let _company = query_as::<_, crate::db::models::Company>(
        "SELECT * FROM companies WHERE id = ?"
    )
        .bind(&cid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Company {} not found", cid)))?;

    recompute_module_difficulty(&state, &cid).await;

    Ok(Json(serde_json::json!({
        "recomputed": true,
        "company_id": cid,
    })))
}

// -- Helpers --

/// Compare success rate of last 10 outcomes vs previous 10.
async fn compute_trend(state: &SharedState, company_id: &str) -> String {
    // Get last 20 outcomes ordered by time
    let recent: Vec<(bool,)> = sqlx::query_as(
        "SELECT io.success FROM issue_outcomes io
         JOIN issues i ON io.issue_id = i.id
         WHERE i.company_id = ?
         ORDER BY io.created_at DESC LIMIT 20"
    )
        .bind(company_id)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    if recent.len() < 4 {
        return "stable".to_string();
    }

    let mid = recent.len() / 2;
    let older = &recent[mid..];
    let newer = &recent[..mid];

    let older_rate = older.iter().filter(|(s,)| *s).count() as f64 / older.len() as f64;
    let newer_rate = newer.iter().filter(|(s,)| *s).count() as f64 / newer.len() as f64;

    let diff = newer_rate - older_rate;
    if diff > 0.15 {
        "improving".to_string()
    } else if diff < -0.15 {
        "declining".to_string()
    } else {
        "stable".to_string()
    }
}

/// Generate actionable recommendations from learnings data.
fn generate_recommendations(
    overall_rate: f64,
    total: i64,
    by_strategy: &[StrategyStats],
    modules: &[ModuleDifficulty],
    trend: &str,
) -> Vec<Recommendation> {
    let mut recs = Vec::new();

    // Trend-based
    if trend == "declining" {
        recs.push(Recommendation {
            kind: "trend".to_string(),
            severity: "critical".to_string(),
            message: "Overall success rate declining -- propose smaller, more targeted changes".to_string(),
        });
    } else if trend == "improving" {
        recs.push(Recommendation {
            kind: "trend".to_string(),
            severity: "info".to_string(),
            message: "Success rate improving -- current approach is working".to_string(),
        });
    }

    // Strategy-based
    for ss in by_strategy {
        if ss.total >= 3 && ss.success_rate >= 90.0 {
            recs.push(Recommendation {
                kind: "strategy".to_string(),
                severity: "info".to_string(),
                message: format!(
                    "{} strategy has {:.0}% success over {} attempts -- keep using it",
                    ss.strategy, ss.success_rate, ss.total
                ),
            });
        }
        if ss.total >= 3 && ss.success_rate < 40.0 {
            recs.push(Recommendation {
                kind: "strategy".to_string(),
                severity: "warning".to_string(),
                message: format!(
                    "{} strategy has {:.0}% success over {} attempts -- consider alternatives",
                    ss.strategy, ss.success_rate, ss.total
                ),
            });
        }
    }

    // Module-based
    for m in modules {
        if m.difficulty == "hard" && m.total_attempts >= 3 {
            recs.push(Recommendation {
                kind: "module".to_string(),
                severity: "warning".to_string(),
                message: format!(
                    "{} has {} failures in {} attempts (hard) -- break into smaller changes",
                    m.file_path, m.failures, m.total_attempts
                ),
            });
        }
    }

    // General
    if total > 0 && overall_rate < 50.0 {
        recs.push(Recommendation {
            kind: "general".to_string(),
            severity: "critical".to_string(),
            message: format!(
                "Overall success rate is {:.0}% -- agents may need better task scoping or smaller issues",
                overall_rate
            ),
        });
    }

    recs
}
