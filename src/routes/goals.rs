use axum::{extract::{Path, State}, response::Json};
use serde::Deserialize;
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::Goal;

#[derive(Debug, Deserialize)]
pub struct CreateGoalRequest {
    pub title: String,
    pub description: Option<String>,
    pub level: Option<String>,
    pub parent_id: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateGoalRequest {
    pub title: Option<String>,
    pub description: Option<String>,
    pub level: Option<String>,
    pub status: Option<String>,
    pub parent_id: Option<String>,
}

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<Goal>>> {
    let goals = query_as::<_, Goal>(
        "SELECT * FROM goals WHERE company_id = ? ORDER BY created_at"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(goals))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateGoalRequest>,
) -> AppResult<Json<Goal>> {
    let id = Uuid::new_v4().to_string();
    let level = body.level.unwrap_or_else(|| "task".to_string());
    let status = "planned".to_string();

    sqlx::query(
        "INSERT INTO goals (id, company_id, title, description, level, status, parent_id)
         VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.title)
        .bind(&body.description)
        .bind(&level)
        .bind(&status)
        .bind(&body.parent_id)
        .execute(&state.pool)
        .await?;

    let goal = query_as::<_, Goal>("SELECT * FROM goals WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(goal))
}

pub async fn update(
    State(state): State<SharedState>,
    Path(gid): Path<String>,
    Json(body): Json<UpdateGoalRequest>,
) -> AppResult<Json<Goal>> {
    let existing = query_as::<_, Goal>("SELECT * FROM goals WHERE id = ?")
        .bind(&gid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Goal {} not found", gid)))?;

    let title = body.title.unwrap_or(existing.title);
    let description = body.description.or(existing.description);
    let level = body.level.unwrap_or(existing.level);
    let status = body.status.unwrap_or(existing.status);
    let parent_id = body.parent_id.or(existing.parent_id);

    sqlx::query(
        "UPDATE goals SET title = ?, description = ?, level = ?, status = ?, parent_id = ?,
         updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&title)
        .bind(&description)
        .bind(&level)
        .bind(&status)
        .bind(&parent_id)
        .bind(&gid)
        .execute(&state.pool)
        .await?;

    let goal = query_as::<_, Goal>("SELECT * FROM goals WHERE id = ?")
        .bind(&gid)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(goal))
}
