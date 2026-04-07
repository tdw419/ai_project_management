use axum::{extract::{Path, State}, response::Json};
use serde::Deserialize;
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::Project;

#[derive(Debug, Deserialize)]
pub struct CreateProjectRequest {
    pub name: String,
    pub description: Option<String>,
    pub color: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateProjectRequest {
    pub name: Option<String>,
    pub description: Option<String>,
    pub status: Option<String>,
    pub color: Option<String>,
}

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<Project>>> {
    let projects = query_as::<_, Project>(
        "SELECT * FROM projects WHERE company_id = ? ORDER BY created_at"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(projects))
}

pub async fn get(
    State(state): State<SharedState>,
    Path(pid): Path<String>,
) -> AppResult<Json<Project>> {
    let project = query_as::<_, Project>("SELECT * FROM projects WHERE id = ?")
        .bind(&pid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Project {} not found", pid)))?;
    Ok(Json(project))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateProjectRequest>,
) -> AppResult<Json<Project>> {
    let id = Uuid::new_v4().to_string();
    let status = "in_progress".to_string();

    sqlx::query(
        "INSERT INTO projects (id, company_id, name, description, status, color)
         VALUES (?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.name)
        .bind(&body.description)
        .bind(&status)
        .bind(&body.color)
        .execute(&state.pool)
        .await?;

    let project = query_as::<_, Project>("SELECT * FROM projects WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(project))
}

pub async fn update(
    State(state): State<SharedState>,
    Path(pid): Path<String>,
    Json(body): Json<UpdateProjectRequest>,
) -> AppResult<Json<Project>> {
    let existing = query_as::<_, Project>("SELECT * FROM projects WHERE id = ?")
        .bind(&pid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Project {} not found", pid)))?;

    let name = body.name.unwrap_or(existing.name);
    let description = body.description.or(existing.description);
    let status = body.status.unwrap_or(existing.status);
    let color = body.color.or(existing.color);

    sqlx::query(
        "UPDATE projects SET name = ?, description = ?, status = ?, color = ?,
         updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&name)
        .bind(&description)
        .bind(&status)
        .bind(&color)
        .bind(&pid)
        .execute(&state.pool)
        .await?;

    let project = query_as::<_, Project>("SELECT * FROM projects WHERE id = ?")
        .bind(&pid)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(project))
}
