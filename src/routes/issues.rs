use axum::{extract::{Path, Query, State}, response::Json};
use serde::Deserialize;
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{Issue, IssueComment, CreateIssueRequest, UpdateIssueRequest, CheckoutRequest, CreateCommentRequest};
use crate::state_machine;

#[derive(Debug, Deserialize)]
pub struct ListParams {
    pub status: Option<String>,
    pub project_id: Option<String>,
    pub assignee_agent_id: Option<String>,
    pub blocked: Option<String>,
}

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Query(params): Query<ListParams>,
) -> AppResult<Json<Vec<Issue>>> {
    let mut sql = String::from("SELECT * FROM issues WHERE company_id = ?");
    let mut bindings: Vec<String> = vec![cid.clone()];

    if let Some(ref status) = params.status {
        sql.push_str(" AND status = ?");
        bindings.push(status.clone());
    }
    if let Some(ref project_id) = params.project_id {
        sql.push_str(" AND project_id = ?");
        bindings.push(project_id.clone());
    }
    if let Some(ref assignee) = params.assignee_agent_id {
        sql.push_str(" AND assignee_agent_id = ?");
        bindings.push(assignee.clone());
    }

    sql.push_str(" ORDER BY created_at DESC");

    let mut query = sqlx::query_as::<_, Issue>(&sql);
    for b in &bindings {
        query = query.bind(b);
    }

    let issues = query.fetch_all(&state.pool).await?;
    Ok(Json(issues))
}

pub async fn get(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
) -> AppResult<Json<Issue>> {
    let issue = resolve_issue(&state, &iid).await?;
    Ok(Json(issue))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateIssueRequest>,
) -> AppResult<Json<Issue>> {
    let id = Uuid::new_v4().to_string();

    // Get company for issue prefix and counter
    let company = sqlx::query_as::<_, crate::db::models::Company>(
        "SELECT * FROM companies WHERE id = ?"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await?;

    // Increment issue counter atomically
    let row: (i64,) = sqlx::query_as(
        "UPDATE companies SET issue_counter = issue_counter + 1, updated_at = datetime('now') WHERE id = ? RETURNING issue_counter"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await?;

    let issue_number = row.0;
    let identifier = format!("{}-{}", company.issue_prefix, issue_number);
    let priority = body.priority.unwrap_or_else(|| "medium".to_string());
    let origin_kind = body.origin_kind.unwrap_or_else(|| "manual".to_string());
    let blocked_by = body.blocked_by
        .map(|v| serde_json::to_string(&v).unwrap_or_else(|_| "[]".to_string()))
        .unwrap_or_else(|| "[]".to_string());

    sqlx::query(
        "INSERT INTO issues (id, company_id, project_id, parent_id, title, description, status, priority,
         assignee_agent_id, identifier, issue_number, origin_kind, origin_id, blocked_by)
         VALUES (?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.project_id)
        .bind(&body.parent_id)
        .bind(&body.title)
        .bind(&body.description)
        .bind(&priority)
        .bind(&body.assignee_agent_id)
        .bind(&identifier)
        .bind(issue_number)
        .bind(&origin_kind)
        .bind(&body.origin_id)
        .bind(&blocked_by)
        .execute(&state.pool)
        .await?;

    let issue = query_as::<_, Issue>("SELECT * FROM issues WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;

    log_activity(&state, &cid, "system", "geo-forge", "issue.created", "issue", &id, None).await;

    Ok(Json(issue))
}

pub async fn update(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
    Json(body): Json<UpdateIssueRequest>,
) -> AppResult<Json<Issue>> {
    let issue = resolve_issue(&state, &iid).await?;

    // Validate status transition if status is changing
    if let Some(ref new_status) = body.status {
        if *new_status != issue.status {
            state_machine::validate_transition(&issue.status, new_status)?;
        }
    }

    let title = body.title.unwrap_or(issue.title.clone());
    let description = body.description.or(issue.description);
    let status = body.status.unwrap_or_else(|| issue.status.clone());
    let old_status = issue.status.clone();
    let priority = body.priority.unwrap_or_else(|| issue.priority.clone());
    let assignee_agent_id = body.assignee_agent_id.or(issue.assignee_agent_id);
    let project_id = body.project_id.or(issue.project_id);
    let blocked_by = body.blocked_by
        .map(|v| serde_json::to_string(&v).unwrap_or_else(|_| "[]".to_string()))
        .or(issue.blocked_by);

    // Set timestamps based on status changes
    let started_at = if status == "in_progress" && old_status != "in_progress" {
        Some(chrono::Utc::now().to_rfc3339())
    } else {
        issue.started_at
    };
    let completed_at = if (status == "done" || status == "cancelled") && old_status != status {
        Some(chrono::Utc::now().to_rfc3339())
    } else {
        issue.completed_at
    };

    sqlx::query(
        "UPDATE issues SET title = ?, description = ?, status = ?, priority = ?,
         assignee_agent_id = ?, project_id = ?, blocked_by = ?,
         started_at = ?, completed_at = ?, updated_at = datetime('now')
         WHERE id = ?"
    )
        .bind(&title)
        .bind(&description)
        .bind(&status)
        .bind(&priority)
        .bind(&assignee_agent_id)
        .bind(&project_id)
        .bind(&blocked_by)
        .bind(&started_at)
        .bind(&completed_at)
        .bind(&issue.id)
        .execute(&state.pool)
        .await?;

    // If issue moved to done, check if any issues it was blocking are now unblocked
    if status == "done" {
            check_unblock_dependents(&state, &issue.company_id, &issue.identifier).await;
    }

    let updated = query_as::<_, Issue>("SELECT * FROM issues WHERE id = ?")
        .bind(&issue.id)
        .fetch_one(&state.pool)
        .await?;

    log_activity(&state, &issue.company_id, "system", "geo-forge", "issue.updated", "issue", &issue.id,
        Some(serde_json::json!({"status": status, "identifier": updated.identifier}).to_string().into())
    ).await;

    Ok(Json(updated))
}

pub async fn checkout(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
    Json(body): Json<CheckoutRequest>,
) -> AppResult<Json<Issue>> {
    let issue = resolve_issue(&state, &iid).await?;

    // Validate expected statuses
    if let Some(ref expected) = body.expected_statuses {
        if !expected.contains(&issue.status) {
            return Err(AppError::Conflict(format!(
                "Issue {} is '{}' but expected one of: {}",
                issue.identifier.clone().unwrap_or_default(),
                issue.status,
                expected.join(", ")
            )));
        }
    }

    // Transition to in_progress and assign
    let now = chrono::Utc::now().to_rfc3339();
    sqlx::query(
        "UPDATE issues SET status = 'in_progress', assignee_agent_id = ?,
         started_at = ?, updated_at = datetime('now') WHERE id = ?"
    )
        .bind(&body.agent_id)
        .bind(&now)
        .bind(&issue.id)
        .execute(&state.pool)
        .await?;

    let updated = query_as::<_, Issue>("SELECT * FROM issues WHERE id = ?")
        .bind(&issue.id)
        .fetch_one(&state.pool)
        .await?;

    log_activity(&state, &issue.company_id, "agent", &body.agent_id, "issue.checked_out", "issue", &issue.id, None).await;

    Ok(Json(updated))
}

pub async fn list_comments(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
) -> AppResult<Json<Vec<IssueComment>>> {
    let issue = resolve_issue(&state, &iid).await?;
    let comments = query_as::<_, IssueComment>(
        "SELECT * FROM issue_comments WHERE issue_id = ? ORDER BY created_at"
    )
        .bind(&issue.id)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(comments))
}

pub async fn create_comment(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
    Json(body): Json<CreateCommentRequest>,
) -> AppResult<Json<IssueComment>> {
    let issue = resolve_issue(&state, &iid).await?;
    let id = Uuid::new_v4().to_string();

    sqlx::query(
        "INSERT INTO issue_comments (id, issue_id, body, author_user_id) VALUES (?, ?, ?, 'board')"
    )
        .bind(&id)
        .bind(&issue.id)
        .bind(&body.body)
        .execute(&state.pool)
        .await?;

    let comment = query_as::<_, IssueComment>("SELECT * FROM issue_comments WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;

    log_activity(&state, &issue.company_id, "user", "board", "issue.comment_added", "issue", &issue.id, None).await;

    Ok(Json(comment))
}

pub async fn blockers(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let issue = resolve_issue(&state, &iid).await?;
    let blocked_by: Vec<String> = issue.blocked_by
        .as_ref()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default();

    if blocked_by.is_empty() {
        return Ok(Json(serde_json::json!({"blockers": [], "blocked": false})));
    }

    // Find which blockers are still unresolved
    let _unresolved: Vec<String> = sqlx::query_scalar(
        "SELECT identifier FROM issues WHERE company_id = ? AND identifier IN (?) AND status NOT IN ('done', 'cancelled')"
    )
        .bind(&issue.company_id)
        // SQLite doesn't support IN with bind params easily, so do it manually
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    // Manual filter since we can't do dynamic IN easily
    let all_blocker_issues = query_as::<_, Issue>(
        &format!(
            "SELECT * FROM issues WHERE company_id = ? AND identifier IN ({})",
            blocked_by.iter().map(|s| format!("'{}'", s)).collect::<Vec<_>>().join(",")
        )
    )
        .bind(&issue.company_id)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    let unresolved: Vec<String> = all_blocker_issues
        .iter()
        .filter(|i| i.status != "done" && i.status != "cancelled")
        .map(|i| i.identifier.clone().unwrap_or_default())
        .collect();

    Ok(Json(serde_json::json!({
        "blockers": unresolved,
        "blocked": !unresolved.is_empty(),
        "allDependencies": blocked_by,
    })))
}

// -- Helpers --

async fn resolve_issue(state: &SharedState, iid: &str) -> AppResult<Issue> {
    // Try as UUID first, then as identifier
    if let Ok(Some(issue)) = query_as::<_, Issue>("SELECT * FROM issues WHERE id = ?")
        .bind(iid)
        .fetch_optional(&state.pool)
        .await
    {
        return Ok(issue);
    }

    query_as::<_, Issue>("SELECT * FROM issues WHERE identifier = ?")
        .bind(iid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Issue {} not found", iid)))
}

async fn check_unblock_dependents(state: &SharedState, company_id: &str, identifier: &Option<String>) {
    if identifier.is_none() { return; }
    let ident = identifier.as_ref().unwrap();

    // Find issues whose blocked_by contains this identifier
    let issues = query_as::<_, Issue>(
        "SELECT * FROM issues WHERE company_id = ? AND status = 'backlog' AND blocked_by LIKE ?"
    )
        .bind(company_id)
        .bind(format!("%{}%", ident))
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    for issue in issues {
        let deps: Vec<String> = issue.blocked_by
            .as_ref()
            .and_then(|s| serde_json::from_str(s).ok())
            .unwrap_or_default();

        // Check if all deps are resolved
        let all_resolved = deps.iter().all(|dep| {
            // Check if this dep is done or cancelled
            // For simplicity, check if the completed identifier is in the deps
            dep == ident || dep.starts_with("done:")
        });

        if all_resolved {
            // Auto-promote to todo
            let _ = sqlx::query(
                "UPDATE issues SET status = 'todo', updated_at = datetime('now') WHERE id = ?"
            )
                .bind(&issue.id)
                .execute(&state.pool)
                .await;

            tracing::info!("Auto-promoted {} to todo (all blockers resolved)", issue.identifier.unwrap_or_default());
        }
    }
}

async fn log_activity(
    state: &SharedState,
    company_id: &str,
    actor_type: &str,
    actor_id: &str,
    action: &str,
    entity_type: &str,
    entity_id: &str,
    details: Option<String>,
) {
    let id = Uuid::new_v4().to_string();
    let _ = sqlx::query(
        "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(company_id)
        .bind(actor_type)
        .bind(actor_id)
        .bind(action)
        .bind(entity_type)
        .bind(entity_id)
        .bind(&details)
        .execute(&state.pool)
        .await;
}
