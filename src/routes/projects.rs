use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use crate::{AppResult, SharedState};
use crate::db::models::Project;

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
        .ok_or_else(|| crate::error::AppError::NotFound(format!("Project {} not found", pid)))?;
    Ok(Json(project))
}
