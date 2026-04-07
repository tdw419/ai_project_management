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
        "UPDATE routines SET title = ?, status = ?, cron_expression = ?, updated_at = datetime('now') WHERE id = ?"
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
