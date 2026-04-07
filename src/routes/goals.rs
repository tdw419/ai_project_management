use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use crate::{AppResult, SharedState};
use crate::db::models::Goal;

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
