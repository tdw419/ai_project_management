use axum::{extract::{Path, Query, State}, response::Json};
use serde::Deserialize;
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{Agent, CreateAgentRequest, UpdateAgentRequest};

#[derive(Debug, Deserialize)]
pub struct ListParams {
    pub status: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Query(params): Query<ListParams>,
) -> AppResult<Json<Vec<Agent>>> {
    let limit = params.limit.unwrap_or(100).min(500);
    let offset = params.offset.unwrap_or(0);

    let mut sql = String::from("SELECT * FROM agents WHERE company_id = ?");
    let mut bindings: Vec<String> = vec![cid.clone()];

    if let Some(ref status) = params.status {
        sql.push_str(" AND status = ?");
        bindings.push(status.clone());
    }

    sql.push_str(" ORDER BY created_at LIMIT ? OFFSET ?");
    bindings.push(limit.to_string());
    bindings.push(offset.to_string());

    let mut query = sqlx::query_as::<_, Agent>(&sql);
    for b in &bindings {
        query = query.bind(b);
    }

    let agents = query.fetch_all(&state.pool).await?;
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
         paused_at = CASE WHEN ? = 'paused' THEN strftime('%Y-%m-%dT%H:%M:%SZ', 'now') ELSE paused_at END,
         updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
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
    sqlx::query("UPDATE agents SET last_heartbeat = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), status = 'running', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?")
        .bind(&aid)
        .execute(&state.pool)
        .await?;

    // Invoke via executor (find next todo issue for this agent)
    let issue = sqlx::query_as::<_, crate::db::models::Issue>(
        "SELECT * FROM issues WHERE assignee_agent_id = ? AND status = 'todo' \
         ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, \
         created_at LIMIT 1"
    )
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?;

    let issue_id = issue.as_ref().map(|i| i.id.clone());
    let issue_id_spawn = issue_id.clone();

    // Spawn the invocation in the background so we can return immediately
    let invoke_state = state.clone();
    let agent_id = aid.to_string();
    tokio::spawn(async move {
        let result = crate::services::executor::invoke_agent(
            &invoke_state,
            &agent_id,
            issue_id_spawn.as_deref(),
            "wakeup",
            None,
        ).await;
        if result.success {
            tracing::info!("Wakeup agent {} completed", agent_id);
        } else {
            tracing::warn!("Wakeup agent {} failed: {}", agent_id, result.output.chars().take(200).collect::<String>());
        }
    });

    Ok(Json(serde_json::json!({
        "status": "accepted",
        "agentId": aid,
        "agentName": agent.name,
        "issueId": issue_id,
    })))
}

/// Explicitly invoke an agent on a specific issue.
pub async fn invoke(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
    Json(body): Json<serde_json::Value>,
) -> AppResult<Json<serde_json::Value>> {
    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    if agent.status == "paused" {
        return Err(AppError::Validation(format!("Agent {} is paused", aid)));
    }

    let issue_id = body.get("issue_id").and_then(|v| v.as_str()).map(String::from);
    let issue_id_spawn = issue_id.clone();

    let invoke_state = state.clone();
    let agent_id = aid.to_string();
    tokio::spawn(async move {
        let result = crate::services::executor::invoke_agent(
            &invoke_state,
            &agent_id,
            issue_id_spawn.as_deref(),
            "invoke",
            None,
        ).await;
        if result.success {
            tracing::info!("Invoke agent {} completed", agent_id);
        } else {
            tracing::warn!("Invoke agent {} failed: {}", agent_id, result.output.chars().take(200).collect::<String>());
        }
    });

    Ok(Json(serde_json::json!({
        "status": "accepted",
        "agentId": aid,
        "agentName": agent.name,
        "issueId": issue_id,
    })))
}

/// Heartbeat: update agent's last_heartbeat timestamp.
/// Agents call this periodically to signal they're alive.
pub async fn heartbeat(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
    Json(body): Json<serde_json::Value>,
) -> AppResult<Json<serde_json::Value>> {
    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    // Optionally accept a status payload
    let status = body.get("status").and_then(|v| v.as_str()).map(String::from);

    let now = chrono::Utc::now().to_rfc3339();
    if let Some(ref s) = status {
        sqlx::query(
            "UPDATE agents SET last_heartbeat = ?, status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
        )
            .bind(&now)
            .bind(s)
            .bind(&aid)
            .execute(&state.pool)
            .await?;
    } else {
        sqlx::query(
            "UPDATE agents SET last_heartbeat = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
        )
            .bind(&now)
            .bind(&aid)
            .execute(&state.pool)
            .await?;
    }

    Ok(Json(serde_json::json!({
        "status": "ok",
        "agentId": aid,
        "agentName": agent.name,
        "heartbeatAt": now,
    })))
}

/// Soft-delete an agent by setting status to 'deleted'.
/// Orphaned issues remain but lose their assignee.
pub async fn delete(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    if agent.status == "deleted" {
        return Err(AppError::Validation(format!("Agent {} already deleted", aid)));
    }

    // Soft-delete the agent
    sqlx::query(
        "UPDATE agents SET status = 'deleted', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&aid)
        .execute(&state.pool)
        .await?;

    // Unassign any issues currently assigned to this agent
    sqlx::query(
        "UPDATE issues SET assignee_agent_id = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') \
         WHERE assignee_agent_id = ? AND status NOT IN ('done', 'cancelled')"
    )
        .bind(&aid)
        .execute(&state.pool)
        .await?;

    Ok(Json(serde_json::json!({
        "status": "deleted",
        "agentId": aid,
        "agentName": agent.name,
    })))
}
