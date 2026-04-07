use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppResult, SharedState};
use crate::db::models::{Routine, CreateRoutineRequest};

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<Routine>>> {
    let routines = query_as::<_, Routine>(
        "SELECT * FROM routines WHERE company_id = ? ORDER BY created_at"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(routines))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateRoutineRequest>,
) -> AppResult<Json<Routine>> {
    let id = Uuid::new_v4().to_string();
    let concurrency = body.concurrency.unwrap_or_else(|| "skip_if_active".to_string());

    sqlx::query(
        "INSERT INTO routines (id, company_id, project_id, title, description, assignee_agent_id, cron_expression, concurrency)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.project_id)
        .bind(&body.title)
        .bind(&body.description)
        .bind(&body.assignee_agent_id)
        .bind(&body.cron_expression)
        .bind(&concurrency)
        .execute(&state.pool)
        .await?;

    let routine = query_as::<_, Routine>("SELECT * FROM routines WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(routine))
}

pub async fn update(
    State(state): State<SharedState>,
    Path(rid): Path<String>,
    Json(body): Json<serde_json::Value>,
) -> AppResult<Json<Routine>> {
    let existing = query_as::<_, Routine>("SELECT * FROM routines WHERE id = ?")
        .bind(&rid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| crate::error::AppError::NotFound(format!("Routine {} not found", rid)))?;

    let title = body.get("title").and_then(|v| v.as_str()).unwrap_or(&existing.title).to_string();
    let status = body.get("status").and_then(|v| v.as_str()).unwrap_or(&existing.status).to_string();
    let cron_expression = body.get("cron_expression").and_then(|v| v.as_str())
        .map(|s| s.to_string()).or(existing.cron_expression);

    sqlx::query(
        "UPDATE routines SET title = ?, status = ?, cron_expression = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&title)
        .bind(&status)
        .bind(&cron_expression)
        .bind(&rid)
        .execute(&state.pool)
        .await?;

    let routine = query_as::<_, Routine>("SELECT * FROM routines WHERE id = ?")
        .bind(&rid)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(routine))
}

/// Manually trigger a routine (bypasses cron schedule).
pub async fn trigger(
    State(state): State<SharedState>,
    Path(rid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let routine = query_as::<_, Routine>("SELECT * FROM routines WHERE id = ?")
        .bind(&rid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| crate::error::AppError::NotFound(format!("Routine {} not found", rid)))?;

    // Find issue for the routine
    let issue = if let Some(ref project_id) = routine.project_id {
        sqlx::query_as::<_, crate::db::models::Issue>(
            "SELECT * FROM issues WHERE company_id = ? AND project_id = ? AND status = 'todo' \
             ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, \
             created_at LIMIT 1"
        )
            .bind(&routine.company_id)
            .bind(project_id)
            .fetch_optional(&state.pool)
            .await?
    } else {
        sqlx::query_as::<_, crate::db::models::Issue>(
            "SELECT * FROM issues WHERE company_id = ? AND (assignee_agent_id = ? OR assignee_agent_id IS NULL) AND status = 'todo' \
             ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, \
             created_at LIMIT 1"
        )
            .bind(&routine.company_id)
            .bind(&routine.assignee_agent_id)
            .fetch_optional(&state.pool)
            .await?
    };

    let issue_id = issue.as_ref().map(|i| i.id.clone());
    let issue_id_spawn = issue_id.clone();

    // Update last_triggered_at
    sqlx::query(
        "UPDATE routines SET last_triggered_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&rid)
        .execute(&state.pool)
        .await?;

    // Spawn invocation in background
    let invoke_state = state.clone();
    let agent_id = routine.assignee_agent_id.clone();
    let rid_spawn = rid.to_string();
    tokio::spawn(async move {
        let result = crate::services::executor::invoke_agent(
            &invoke_state,
            &agent_id,
            issue_id_spawn.as_deref(),
            "routine",
            Some(&rid_spawn),
        ).await;
        if result.success {
            tracing::info!("Routine trigger for agent {} completed", agent_id);
        } else {
            tracing::warn!("Routine trigger for agent {} failed: {}", agent_id, result.output.chars().take(200).collect::<String>());
        }
    });

    Ok(Json(serde_json::json!({
        "status": "accepted",
        "routineId": rid,
        "agentId": routine.assignee_agent_id,
        "issueId": issue_id,
    })))
}

/// Deactivate a routine by setting status to 'inactive'.
pub async fn delete(
    State(state): State<SharedState>,
    Path(rid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let routine = query_as::<_, Routine>("SELECT * FROM routines WHERE id = ?")
        .bind(&rid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| crate::error::AppError::NotFound(format!("Routine {} not found", rid)))?;

    if routine.status == "inactive" {
        return Err(crate::error::AppError::Validation(format!("Routine {} already inactive", rid)));
    }

    sqlx::query(
        "UPDATE routines SET status = 'inactive', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&rid)
        .execute(&state.pool)
        .await?;

    Ok(Json(serde_json::json!({
        "status": "inactive",
        "routineId": rid,
        "title": routine.title,
    })))
}
