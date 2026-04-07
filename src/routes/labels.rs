use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppResult, SharedState};
use crate::db::models::Label;

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<Label>>> {
    let labels = query_as::<_, Label>(
        "SELECT * FROM labels WHERE company_id = ? ORDER BY created_at"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(labels))
}

#[derive(serde::Deserialize)]
pub struct CreateLabelRequest {
    pub name: String,
    pub color: String,
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateLabelRequest>,
) -> AppResult<Json<Label>> {
    let id = Uuid::new_v4().to_string();

    sqlx::query("INSERT INTO labels (id, company_id, name, color) VALUES (?, ?, ?, ?)")
        .bind(&id)
        .bind(&cid)
        .bind(&body.name)
        .bind(&body.color)
        .execute(&state.pool)
        .await?;

    let label = query_as::<_, Label>("SELECT * FROM labels WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(label))
}
