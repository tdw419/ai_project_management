use axum::{extract::{Path, Query, State}, response::Json};
use serde::Deserialize;
use crate::{AppResult, SharedState};
use crate::db::models::ActivityLog;

#[derive(Debug, Deserialize)]
pub struct ActivityParams {
    pub entity_type: Option<String>,
    pub actor_id: Option<String>,
    pub limit: Option<i64>,
}

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Query(params): Query<ActivityParams>,
) -> AppResult<Json<Vec<ActivityLog>>> {
    let limit = params.limit.unwrap_or(100).min(500);
    let mut sql = String::from("SELECT * FROM activity_log WHERE company_id = ?");
    let mut bindings: Vec<String> = vec![cid.clone()];

    if let Some(ref entity_type) = params.entity_type {
        sql.push_str(" AND entity_type = ?");
        bindings.push(entity_type.clone());
    }
    if let Some(ref actor_id) = params.actor_id {
        sql.push_str(" AND actor_id = ?");
        bindings.push(actor_id.clone());
    }

    sql.push_str(" ORDER BY created_at DESC LIMIT ?");
    bindings.push(limit.to_string());

    let mut query = sqlx::query_as::<_, ActivityLog>(&sql);
    for b in &bindings {
        query = query.bind(b);
    }

    let activity = query.fetch_all(&state.pool).await?;
    Ok(Json(activity))
}
