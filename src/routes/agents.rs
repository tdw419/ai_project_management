use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{Agent, CreateAgentRequest, UpdateAgentRequest};

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<Agent>>> {
    let agents = query_as::<_, Agent>(
        "SELECT * FROM agents WHERE company_id = ? ORDER BY created_at"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(agents))
}

pub async fn get(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
) -> AppResult<Json<Agent>> {
    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;
    Ok(Json(agent))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateAgentRequest>,
) -> AppResult<Json<Agent>> {
    let id = Uuid::new_v4().to_string();
    let role = body.role.unwrap_or_else(|| "general".to_string());
    let adapter_type = body.adapter_type.unwrap_or_else(|| "hermes_local".to_string());
    let adapter_config = body.adapter_config
        .map(|v| v.to_string())
        .unwrap_or_else(|| "{}".to_string());
    let runtime_config = body.runtime_config
        .map(|v| v.to_string())
        .unwrap_or_else(|| "{}".to_string());
    let permissions = body.permissions
        .map(|v| v.to_string())
        .unwrap_or_else(|| "{}".to_string());

    sqlx::query(
        "INSERT INTO agents (id, company_id, name, role, adapter_type, adapter_config, runtime_config, reports_to, permissions)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.name)
        .bind(&role)
        .bind(&adapter_type)
        .bind(&adapter_config)
        .bind(&runtime_config)
        .bind(&body.reports_to)
        .bind(&permissions)
        .execute(&state.pool)
        .await?;

    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(agent))
}

pub async fn update(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
    Json(body): Json<UpdateAgentRequest>,
) -> AppResult<Json<Agent>> {
    let existing = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    let name = body.name.unwrap_or(existing.name);
    let role = body.role.unwrap_or(existing.role);
    let status = body.status.unwrap_or(existing.status);
    let adapter_type = body.adapter_type.unwrap_or(existing.adapter_type);
    let adapter_config = body.adapter_config
        .map(|v| v.to_string())
        .unwrap_or(existing.adapter_config);
    let runtime_config = body.runtime_config
        .map(|v| v.to_string())
        .unwrap_or(existing.runtime_config);
    let permissions = body.permissions
        .map(|v| v.to_string())
        .unwrap_or(existing.permissions);

    sqlx::query(
        "UPDATE agents SET name = ?, role = ?, status = ?, adapter_type = ?,
         adapter_config = ?, runtime_config = ?, permissions = ?,
         paused_at = CASE WHEN ? = 'paused' THEN datetime('now') ELSE paused_at END,
         updated_at = datetime('now')
         WHERE id = ?"
    )
        .bind(&name)
        .bind(&role)
        .bind(&status)
        .bind(&adapter_type)
        .bind(&adapter_config)
        .bind(&runtime_config)
        .bind(&permissions)
        .bind(&status)
        .bind(&aid)
        .execute(&state.pool)
        .await?;

    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(agent))
}

pub async fn wakeup(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    if agent.status == "paused" {
        return Err(AppError::Validation(format!("Agent {} is paused", aid)));
    }

    // Update last_heartbeat timestamp
    sqlx::query("UPDATE agents SET last_heartbeat = datetime('now'), status = 'running', updated_at = datetime('now') WHERE id = ?")
        .bind(&aid)
        .execute(&state.pool)
        .await?;

    // TODO: Actually invoke the agent's adapter (hermes_local, etc)
    // For now, just log the wakeup
    tracing::info!("Wakeup requested for agent {} ({})", agent.name, aid);

    Ok(Json(serde_json::json!({
        "status": "accepted",
        "agentId": aid,
        "agentName": agent.name,
    })))
}
