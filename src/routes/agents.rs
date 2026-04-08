use axum::{extract::{Path, Query, State}, response::Json};
use serde::Deserialize;
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{Agent, CreateAgentRequest, UpdateAgentRequest, RegisterAgentRequest};

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
    crate::validation::require_non_empty(&body.name, "name")?;
    crate::validation::validate_length(&body.name, "name", crate::validation::MAX_NAME_LEN)?;
    crate::validation::validate_opt_enum(&body.role, "role", crate::validation::VALID_AGENT_ROLES)?;

    let id = Uuid::new_v4().to_string();
    let role = body.role.unwrap_or_else(|| "general".to_string());
    let adapter_type = body.adapter_type.unwrap_or_else(|| "geo_harness".to_string());
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

/// Agent registration handshake.
/// An agent announces itself with a capabilities manifest.
/// GeoForge creates or re-activates the agent record, then assigns any
/// backlogged todo issues matching the agent's role.
///
/// Returns the agent record + list of auto-assigned issues.
pub async fn register(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<RegisterAgentRequest>,
) -> AppResult<Json<serde_json::Value>> {
    let role = body.role.unwrap_or_else(|| "general".to_string());
    let adapter_type = body.adapter_type.unwrap_or_else(|| "geo_harness".to_string());
    let adapter_config = body.adapter_config
        .map(|v| v.to_string())
        .unwrap_or_else(|| "{}".to_string());

    // Build runtime_config with capabilities
    let mut rt_config = serde_json::json!({});
    if let Some(ref caps) = body.capabilities {
        rt_config["capabilities"] = serde_json::Value::Array(
            caps.iter().map(|c| serde_json::Value::String(c.clone())).collect()
        );
    }
    let rt_config_str = rt_config.to_string();

    // Re-registration: if agent_id provided and exists, reactivate
    let agent = if let Some(ref existing_id) = body.agent_id {
        let existing = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ? AND company_id = ?")
            .bind(existing_id)
            .bind(&cid)
            .fetch_optional(&state.pool)
            .await?;

        if let Some(mut a) = existing {
            // Reactivate: update status, capabilities, heartbeat
            sqlx::query(
                "UPDATE agents SET name = ?, role = ?, status = 'idle', adapter_type = ?,\
                 adapter_config = ?, runtime_config = ?, last_heartbeat = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),\
                 error_message = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(&body.name)
                .bind(&role)
                .bind(&adapter_type)
                .bind(&adapter_config)
                .bind(&rt_config_str)
                .bind(existing_id)
                .execute(&state.pool)
                .await?;

            a = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
                .bind(existing_id)
                .fetch_one(&state.pool)
                .await?;

            // Log re-registration
            let activity_id = Uuid::new_v4().to_string();
            let _ = sqlx::query(
                "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)\
                 VALUES (?, ?, 'agent', ?, 'register', 'agent', ?, ?)"
            )
                .bind(&activity_id)
                .bind(&cid)
                .bind(&a.id)
                .bind(&a.id)
                .bind(serde_json::json!({"re_register": true, "capabilities": body.capabilities}).to_string())
                .execute(&state.pool)
                .await;

            Some(a)
        } else {
            None
        }
    } else {
        None
    };

    // Create new agent if not re-registered
    let agent = match agent {
        Some(a) => a,
        None => {
            let id = Uuid::new_v4().to_string();
            sqlx::query(
                "INSERT INTO agents (id, company_id, name, role, status, adapter_type, adapter_config, runtime_config, permissions, last_heartbeat)\
                 VALUES (?, ?, ?, ?, 'idle', ?, ?, ?, '{}', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
            )
                .bind(&id)
                .bind(&cid)
                .bind(&body.name)
                .bind(&role)
                .bind(&adapter_type)
                .bind(&adapter_config)
                .bind(&rt_config_str)
                .execute(&state.pool)
                .await?;

            // Log registration
            let activity_id = Uuid::new_v4().to_string();
            let _ = sqlx::query(
                "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)\
                 VALUES (?, ?, 'agent', ?, 'register', 'agent', ?, ?)"
            )
                .bind(&activity_id)
                .bind(&cid)
                .bind(&id)
                .bind(&id)
                .bind(serde_json::json!({"capabilities": body.capabilities}).to_string())
                .execute(&state.pool)
                .await;

            query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
                .bind(&id)
                .fetch_one(&state.pool)
                .await?
        }
    };

    // Auto-assign backlogged todo issues matching this agent's role
    let assigned = assign_backlog(&state, &agent).await?;

    tracing::info!(
        "Agent {} ({}) registered with {} capabilities, {} issues auto-assigned",
        agent.name,
        agent.id,
        body.capabilities.map(|c| c.len()).unwrap_or(0),
        assigned.len(),
    );

    Ok(Json(serde_json::json!({
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "status": agent.status,
        },
        "assignedIssues": assigned.iter().map(|i| serde_json::json!({
            "id": i.id,
            "identifier": i.identifier,
            "title": i.title,
        })).collect::<Vec<_>>(),
    })))
}

/// Assign backlogged todo issues to a newly registered agent.
/// Matches unassigned todo issues in the same company, ordered by priority.
async fn assign_backlog(
    state: &SharedState,
    agent: &Agent,
) -> Result<Vec<crate::db::models::Issue>, sqlx::Error> {
    // Find unassigned todo issues (max 5 to avoid overloading)
    let issues = sqlx::query_as::<_, crate::db::models::Issue>(
        "SELECT * FROM issues WHERE company_id = ? AND assignee_agent_id IS NULL AND status = 'todo'\
         ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,\
         created_at LIMIT 5"
    )
        .bind(&agent.company_id)
        .fetch_all(&state.pool)
        .await?;

    let mut assigned = Vec::new();
    for issue in &issues {
        let result = sqlx::query(
            "UPDATE issues SET assignee_agent_id = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')\
             WHERE id = ? AND assignee_agent_id IS NULL"
        )
            .bind(&agent.id)
            .bind(&issue.id)
            .execute(&state.pool)
            .await;

        if let Ok(r) = result {
            if r.rows_affected() > 0 {
                // Log the auto-assignment
                let activity_id = Uuid::new_v4().to_string();
                let _ = sqlx::query(
                    "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)\
                     VALUES (?, ?, 'system', ?, 'auto_assign', 'issue', ?, ?)"
                )
                    .bind(&activity_id)
                    .bind(&agent.company_id)
                    .bind(&agent.id)
                    .bind(&issue.id)
                    .bind(serde_json::json!({"reason": "registration_backlog", "agent": agent.name}).to_string())
                    .execute(&state.pool)
                    .await;

                assigned.push(issue.clone());
            }
        }
    }

    Ok(assigned)
}

pub async fn update(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
    Json(body): Json<UpdateAgentRequest>,
) -> AppResult<Json<Agent>> {
    crate::validation::validate_opt_enum(&body.status, "status", crate::validation::VALID_AGENT_STATUSES)?;
    crate::validation::validate_opt_enum(&body.role, "role", crate::validation::VALID_AGENT_ROLES)?;
    if let Some(ref name) = body.name {
        crate::validation::require_non_empty(name, "name")?;
        crate::validation::validate_length(name, "name", crate::validation::MAX_NAME_LEN)?;
    }

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

/// Heartbeat: update agent's last_heartbeat timestamp with optional status payload.
/// Agents call this periodically to signal they're alive and report progress.
///
/// Payload fields:
///   - `status`: agent status ("running", "idle", "error")
///   - `current_issue_id`: issue the agent is currently working on
///   - `progress_notes`: free-text progress update
///   - `capabilities`: JSON array of capability strings (stored in runtime_config)
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

    let status = body.get("status").and_then(|v| v.as_str()).map(String::from);
    let current_issue_id = body.get("current_issue_id").and_then(|v| v.as_str()).map(String::from);
    let progress_notes = body.get("progress_notes").and_then(|v| v.as_str()).map(String::from);
    let capabilities = body.get("capabilities").and_then(|v| v.as_array()).cloned();

    let now = chrono::Utc::now().to_rfc3339();

    // Update agent status and heartbeat
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

    // Update runtime_config with capabilities if provided
    if let Some(ref caps) = capabilities {
        let mut rt_config: serde_json::Value =
            serde_json::from_str(&agent.runtime_config).unwrap_or(serde_json::json!({}));
        rt_config["capabilities"] = serde_json::Value::Array(caps.clone());
        let config_str = rt_config.to_string();
        sqlx::query(
            "UPDATE agents SET runtime_config = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
        )
            .bind(&config_str)
            .bind(&aid)
            .execute(&state.pool)
            .await?;
    }

    // Log to activity if progress notes or issue change provided
    if progress_notes.is_some() || current_issue_id.is_some() {
        let mut details = serde_json::Map::new();
        if let Some(ref notes) = progress_notes {
            details.insert("progress_notes".into(), serde_json::Value::String(notes.clone()));
        }
        if let Some(ref iid) = current_issue_id {
            details.insert("current_issue_id".into(), serde_json::Value::String(iid.clone()));
        }

        let activity_id = Uuid::new_v4().to_string();
        let _ = sqlx::query(
            "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)\
             VALUES (?, ?, 'agent', ?, 'heartbeat', 'agent', ?, ?)"
        )
            .bind(&activity_id)
            .bind(&agent.company_id)
            .bind(&aid)
            .bind(&aid)
            .bind(serde_json::Value::Object(details).to_string())
            .execute(&state.pool)
            .await;
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

// ── V2-P3: Human Injection Channel ────────────────────────────────────────

#[derive(Debug, serde::Deserialize)]
pub struct InjectRequest {
    pub message: String,
    #[serde(default = "default_priority")]
    pub priority: String,
    #[serde(default = "default_source")]
    pub source: String,
}

fn default_priority() -> String { "normal".to_string() }
fn default_source() -> String { "human".to_string() }

/// Inject a guidance message into an agent's context.
/// The harness picks up unread injections on each loop iteration.
/// POST /api/agents/{aid}/inject
pub async fn inject(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
    Json(body): Json<InjectRequest>,
) -> AppResult<Json<serde_json::Value>> {
    // Verify agent exists
    let agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    crate::validation::require_non_empty(&body.message, "message")?;
    crate::validation::validate_opt_enum(
        &Some(body.priority.clone()),
        "priority",
        &["low", "normal", "high", "urgent"],
    )?;
    crate::validation::validate_opt_enum(
        &Some(body.source.clone()),
        "source",
        &["human", "system", "overseer"],
    )?;

    let id = Uuid::new_v4().to_string();

    sqlx::query(
        "INSERT INTO agent_injections (id, agent_id, message, priority, source) VALUES (?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&aid)
        .bind(&body.message)
        .bind(&body.priority)
        .bind(&body.source)
        .execute(&state.pool)
        .await?;

    // Log the injection
    let activity_id = Uuid::new_v4().to_string();
    let _ = sqlx::query(
        "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)\
         VALUES (?, ?, 'human', ?, 'inject', 'agent', ?, ?)"
    )
        .bind(&activity_id)
        .bind(&agent.company_id)
        .bind(&aid)
        .bind(&id)
        .bind(serde_json::json!({
            "message_preview": body.message.chars().take(100).collect::<String>(),
            "priority": body.priority,
        }).to_string())
        .execute(&state.pool)
        .await;

    tracing::info!(
        "Injection queued for agent {} ({}): [{}] {}",
        agent.name, aid, body.priority,
        body.message.chars().take(80).collect::<String>()
    );

    Ok(Json(serde_json::json!({
        "id": id,
        "agentId": aid,
        "agentName": agent.name,
        "status": "queued",
        "priority": body.priority,
    })))
}

/// Poll for unread injections for an agent.
/// Returns unread messages and marks them as read.
/// GET /api/agents/{aid}/injections
pub async fn poll_injections(
    State(state): State<SharedState>,
    Path(aid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    // Verify agent exists
    let _agent = query_as::<_, Agent>("SELECT * FROM agents WHERE id = ?")
        .bind(&aid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Agent {} not found", aid)))?;

    // Fetch unread injections, ordered by priority then creation time
    let injections = sqlx::query_as::<_, (String, String, String, String, String, String)>(
        "SELECT id, message, priority, source, created_at, read_at \
         FROM agent_injections \
         WHERE agent_id = ? AND read = 0 \
         ORDER BY CASE priority \
             WHEN 'urgent' THEN 0 \
             WHEN 'high' THEN 1 \
             WHEN 'normal' THEN 2 \
             ELSE 3 \
         END, created_at"
    )
        .bind(&aid)
        .fetch_all(&state.pool)
        .await?;

    let count = injections.len();

    // Mark all as read
    if count > 0 {
        sqlx::query(
            "UPDATE agent_injections SET read = 1, read_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') \
             WHERE agent_id = ? AND read = 0"
        )
            .bind(&aid)
            .execute(&state.pool)
            .await?;
    }

    let results: Vec<serde_json::Value> = injections.into_iter().map(|(id, message, priority, source, created_at, _read_at)| {
        serde_json::json!({
            "id": id,
            "message": message,
            "priority": priority,
            "source": source,
            "created_at": created_at,
        })
    }).collect();

    Ok(Json(serde_json::json!({
        "agentId": aid,
        "count": count,
        "injections": results,
    })))
}
