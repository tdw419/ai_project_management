use axum::{extract::{Path, State}, response::Json};
use serde_json::{json, Value};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppResult, SharedState};
use crate::db::models::{Company, AgentSummary, TaskSummary, CreateCompanyRequest};

pub async fn list(State(state): State<SharedState>) -> AppResult<Json<Vec<Company>>> {
    let companies = query_as::<_, Company>("SELECT * FROM companies ORDER BY created_at")
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(companies))
}

pub async fn create(
    State(state): State<SharedState>,
    Json(body): Json<CreateCompanyRequest>,
) -> AppResult<Json<Company>> {
    crate::validation::require_non_empty(&body.name, "name")?;
    crate::validation::validate_length(&body.name, "name", crate::validation::MAX_NAME_LEN)?;
    crate::validation::validate_opt_length(&body.description, "description", crate::validation::MAX_DESCRIPTION_LEN)?;
    crate::validation::validate_opt_prefix(&body.issue_prefix)?;

    let id = Uuid::new_v4().to_string();
    let issue_prefix = body.issue_prefix.unwrap_or_else(|| "GEO".to_string());
    let qa_gate = body.qa_gate.unwrap_or(true);

    sqlx::query(
        "INSERT INTO companies (id, name, description, issue_prefix, qa_gate) VALUES (?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&body.name)
        .bind(&body.description)
        .bind(&issue_prefix)
        .bind(qa_gate)
        .execute(&state.pool)
        .await?;

    let company = query_as::<_, Company>("SELECT * FROM companies WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(company))
}

pub async fn get(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Company>> {
    let company = query_as::<_, Company>("SELECT * FROM companies WHERE id = ?")
        .bind(&cid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| crate::error::AppError::NotFound(format!("Company {} not found", cid)))?;
    Ok(Json(company))
}

pub async fn dashboard(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Value>> {
    // Agent summary
    let agent_counts: Vec<(String, i64)> = sqlx::query_as(
        "SELECT status, COUNT(*) as cnt FROM agents WHERE company_id = ? GROUP BY status"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;

    let mut agents = AgentSummary { active: 0, idle: 0, paused: 0, error: 0 };
    for (status, count) in agent_counts {
        match status.as_str() {
            "running" => agents.active = count,
            "idle" => agents.idle = count,
            "paused" => agents.paused = count,
            "error" => agents.error = count,
            _ => {}
        }
    }

    // Task summary
    let task_counts: Vec<(String, i64)> = sqlx::query_as(
        "SELECT status, COUNT(*) as cnt FROM issues WHERE company_id = ? GROUP BY status"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;

    let mut tasks = TaskSummary {
        backlog: 0, todo: 0, in_progress: 0, in_review: 0, done: 0, cancelled: 0,
    };
    for (status, count) in task_counts {
        match status.as_str() {
            "backlog" => tasks.backlog = count,
            "todo" => tasks.todo = count,
            "in_progress" => tasks.in_progress = count,
            "in_review" => tasks.in_review = count,
            "done" => tasks.done = count,
            "cancelled" => tasks.cancelled = count,
            _ => {}
        }
    }

    // --- P7-A: Operational metrics ---

    // Throughput: issues created and resolved per day, last 7 days
    let throughput: Vec<(String, i64, i64)> = sqlx::query_as(
        "SELECT date(created_at) as day, COUNT(*) as created, 0 as resolved \
         FROM issues WHERE company_id = ? AND created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days') \
         GROUP BY date(created_at) \
         UNION ALL \
         SELECT date(completed_at) as day, 0 as created, COUNT(*) as resolved \
         FROM issues WHERE company_id = ? AND completed_at IS NOT NULL \
         AND completed_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days') \
         AND status IN ('done', 'cancelled') \
         GROUP BY date(completed_at) \
         ORDER BY day"
    )
        .bind(&cid)
        .bind(&cid)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    // Merge rows with same day (created vs resolved come as separate rows from UNION)
    let mut throughput_map: std::collections::BTreeMap<String, (i64, i64)> = std::collections::BTreeMap::new();
    for (day, created, resolved) in throughput {
        let entry = throughput_map.entry(day).or_insert((0, 0));
        entry.0 += created;
        entry.1 += resolved;
    }
    let throughput_json: Vec<Value> = throughput_map.into_iter().map(|(day, (c, r))| {
        json!({"day": day, "created": c, "resolved": r})
    }).collect();

    // Agent utilization: % of agents currently active
    let total_agents = agents.active + agents.idle + agents.paused + agents.error;
    let utilization_pct = if total_agents > 0 {
        (agents.active as f64 / total_agents as f64 * 100.0 * 10.0).round() / 10.0
    } else {
        0.0
    };

    // Bottleneck detection: issues stuck in in_review or in_progress > 24h
    let bottlenecks: Vec<(String, String, String)> = sqlx::query_as(
        "SELECT identifier, title, status FROM issues \
         WHERE company_id = ? AND status IN ('in_review', 'in_progress') \
         AND updated_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-24 hours') \
         ORDER BY updated_at ASC LIMIT 10"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    let bottlenecks_json: Vec<Value> = bottlenecks.into_iter().map(|(ident, title, status)| {
        json!({"identifier": ident, "title": title, "status": status})
    }).collect();

    // Blocker chains: issues in backlog that are blocked by other backlog/todo issues
    let blocker_chain_issues: Vec<crate::db::models::Issue> = sqlx::query_as::<_, crate::db::models::Issue>(
        "SELECT * FROM issues WHERE company_id = ? AND status = 'backlog' AND blocked_by != '[]'"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    let mut blocker_chains: Vec<Value> = Vec::new();
    for issue in &blocker_chain_issues {
        let deps: Vec<String> = issue.blocked_by
            .as_ref()
            .and_then(|s| serde_json::from_str(s).ok())
            .unwrap_or_default();
        let ident = issue.identifier.clone().unwrap_or_default();
        blocker_chains.push(json!({
            "identifier": ident,
            "title": issue.title,
            "blockedBy": deps,
        }));
    }

    // --- P9: Outcome verification stats ---
    let total_outcomes: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM issue_outcomes io JOIN issues i ON io.issue_id = i.id WHERE i.company_id = ?"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    let successful_outcomes: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM issue_outcomes io JOIN issues i ON io.issue_id = i.id WHERE i.company_id = ? AND io.success = 1"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    let verification_rate = if total_outcomes.0 > 0 {
        (successful_outcomes.0 as f64 / total_outcomes.0 as f64 * 100.0 * 10.0).round() / 10.0
    } else {
        0.0
    };

    let avg_test_delta: (f64,) = sqlx::query_as(
        "SELECT COALESCE(AVG(CAST(tests_after - tests_before AS REAL)), 0.0) FROM issue_outcomes io JOIN issues i ON io.issue_id = i.id WHERE i.company_id = ?"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0.0,));

    let recent_failures: Vec<(String, String, String)> = sqlx::query_as(
        "SELECT i.identifier, i.title, io.summary FROM issue_outcomes io \
         JOIN issues i ON io.issue_id = i.id \
         WHERE i.company_id = ? AND io.success = 0 \
         ORDER BY io.created_at DESC LIMIT 5"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    let recent_failures_json: Vec<Value> = recent_failures.into_iter().map(|(ident, title, summary)| {
        json!({"identifier": ident, "title": title, "summary": summary})
    }).collect();

    Ok(Json(json!({
        "companyId": cid,
        "agents": agents,
        "tasks": tasks,
        "metrics": {
            "throughput": throughput_json,
            "agentUtilization": utilization_pct,
            "bottlenecks": bottlenecks_json,
            "blockerChains": blocker_chains,
        },
        "outcomes": {
            "total": total_outcomes.0,
            "successful": successful_outcomes.0,
            "verificationRate": verification_rate,
            "avgTestDelta": avg_test_delta.0,
            "recentFailures": recent_failures_json,
        }
    })))
}
