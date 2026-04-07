use axum::{extract::{Path, Query, State}, response::Json};
use serde::Deserialize;
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{Issue, IssueComment, IssueOutcome, CreateIssueRequest, UpdateIssueRequest, CheckoutRequest, CreateCommentRequest, VerifyOutcomeRequest};
use crate::state_machine;

#[derive(Debug, Deserialize)]
pub struct ListParams {
    pub status: Option<String>,
    pub project_id: Option<String>,
    pub assignee_agent_id: Option<String>,
    pub blocked: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
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

    let limit = params.limit.unwrap_or(100).min(500);
    let offset = params.offset.unwrap_or(0);
    sql.push_str(" LIMIT ? OFFSET ?");
    bindings.push(limit.to_string());
    bindings.push(offset.to_string());

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
) -> AppResult<Json<serde_json::Value>> {
    let issue = resolve_issue(&state, &iid).await?;

    // Fetch latest outcome for this issue (if any)
    let latest_outcome = query_as::<_, IssueOutcome>(
        "SELECT * FROM issue_outcomes WHERE issue_id = ? ORDER BY created_at DESC LIMIT 1"
    )
        .bind(&issue.id)
        .fetch_optional(&state.pool)
        .await?;

    let mut issue_json = serde_json::to_value(&issue)
        .map_err(|e| crate::error::AppError::Internal(format!("serialize issue: {}", e)))?;

    if let Some(obj) = issue_json.as_object_mut() {
        obj.insert("latest_outcome".to_string(), match latest_outcome {
            Some(o) => serde_json::to_value(o).unwrap_or(serde_json::Value::Null),
            None => serde_json::Value::Null,
        });
    }

    Ok(Json(issue_json))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateIssueRequest>,
) -> AppResult<Json<Issue>> {
    crate::validation::require_non_empty(&body.title, "title")?;
    crate::validation::validate_length(&body.title, "title", crate::validation::MAX_TITLE_LEN)?;
    crate::validation::validate_opt_length(&body.description, "description", crate::validation::MAX_DESCRIPTION_LEN)?;
    crate::validation::validate_opt_enum(&body.priority, "priority", crate::validation::VALID_PRIORITIES)?;

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
        "UPDATE companies SET issue_counter = issue_counter + 1, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ? RETURNING issue_counter"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await?;

    let issue_number = row.0;
    let identifier = format!("{}-{}", company.issue_prefix, issue_number);
    let priority = body.priority.unwrap_or_else(|| "medium".to_string());
    let origin_kind = body.origin_kind.unwrap_or_else(|| "manual".to_string());

    // Validate blocked_by identifiers exist in this company
    if let Some(ref deps) = body.blocked_by {
        validate_blocked_by(&state, &cid, deps).await?;
    }

    // Check if issue has blockers before consuming body.blocked_by
    let has_blockers = body.blocked_by.as_ref().map_or(false, |v| !v.is_empty());

    let blocked_by = body.blocked_by
        .map(|v| serde_json::to_string(&v).unwrap_or_else(|_| "[]".to_string()))
        .unwrap_or_else(|| "[]".to_string());

    // Issues with blockers start in 'backlog'; unblocked issues start in 'todo'
    let initial_status = if has_blockers { "backlog" } else { "todo" };

    sqlx::query(
        "INSERT INTO issues (id, company_id, project_id, parent_id, title, description, status, priority,
         assignee_agent_id, identifier, issue_number, origin_kind, origin_id, blocked_by)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.project_id)
        .bind(&body.parent_id)
        .bind(&body.title)
        .bind(&body.description)
        .bind(&initial_status)
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
    // Validate provided fields
    if let Some(ref title) = body.title {
        crate::validation::require_non_empty(title, "title")?;
        crate::validation::validate_length(title, "title", crate::validation::MAX_TITLE_LEN)?;
    }
    crate::validation::validate_opt_length(&body.description, "description", crate::validation::MAX_DESCRIPTION_LEN)?;
    crate::validation::validate_opt_enum(&body.priority, "priority", crate::validation::VALID_PRIORITIES)?;

    let issue = resolve_issue(&state, &iid).await?;

    // Validate status transition if status is changing
    if let Some(ref new_status) = body.status {
        if *new_status != issue.status {
            // Fetch company for qa_gate setting
            let company = sqlx::query_as::<_, crate::db::models::Company>(
                "SELECT * FROM companies WHERE id = ?"
            )
                .bind(&issue.company_id)
                .fetch_one(&state.pool)
                .await?;
            state_machine::validate_transition(&issue.status, new_status, company.qa_gate)?;
        }
    }

    let title = body.title.unwrap_or(issue.title.clone());
    let description = body.description.or(issue.description);
    let status = body.status.unwrap_or_else(|| issue.status.clone());
    let old_status = issue.status.clone();
    let priority = body.priority.unwrap_or_else(|| issue.priority.clone());
    let assignee_agent_id = body.assignee_agent_id.or(issue.assignee_agent_id);
    let project_id = body.project_id.or(issue.project_id);

    // Validate blocked_by identifiers exist in this company (if changed)
    if let Some(ref deps) = body.blocked_by {
        validate_blocked_by(&state, &issue.company_id, deps).await?;
    }

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
         started_at = ?, completed_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
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

    // If issue moved to done/cancelled, check if any issues it was blocking are now unblocked
    if status == "done" || status == "cancelled" {
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

/// Soft-delete an issue by setting status to 'cancelled'.
pub async fn delete(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let issue = resolve_issue(&state, &iid).await?;

    if issue.status == "cancelled" {
        return Err(crate::error::AppError::Validation(format!(
            "Issue {} already cancelled",
            issue.identifier.as_deref().unwrap_or(&issue.id)
        )));
    }
    if issue.status == "done" {
        return Err(crate::error::AppError::Validation(format!(
            "Cannot delete completed issue {}",
            issue.identifier.as_deref().unwrap_or(&issue.id)
        )));
    }

    let now = chrono::Utc::now().to_rfc3339();
    sqlx::query(
        "UPDATE issues SET status = 'cancelled', completed_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&now)
        .bind(&issue.id)
        .execute(&state.pool)
        .await?;

    log_activity(&state, &issue.company_id, "system", "geo-forge", "issue.deleted", "issue", &issue.id, None).await;

    Ok(Json(serde_json::json!({
        "status": "cancelled",
        "issueId": issue.id,
        "identifier": issue.identifier,
    })))
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
         started_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
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
    crate::validation::require_non_empty(&body.body, "body")?;
    crate::validation::validate_length(&body.body, "body", crate::validation::MAX_COMMENT_LEN)?;

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

    // Fetch ALL issues for this company and filter in Rust to avoid SQL injection.
    // SQLite doesn't support dynamic IN() with parameterized queries anyway.
    let all_company_issues = query_as::<_, Issue>(
        "SELECT * FROM issues WHERE company_id = ?"
    )
        .bind(&issue.company_id)
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    let unresolved: Vec<String> = all_company_issues
        .iter()
        .filter(|i| {
            // Must be in the blocked_by list AND not resolved
            i.identifier.as_ref().map_or(false, |ident| blocked_by.contains(ident))
                && i.status != "done"
                && i.status != "cancelled"
        })
        .filter_map(|i| i.identifier.clone())
        .collect();

    Ok(Json(serde_json::json!({
        "blockers": unresolved,
        "blocked": !unresolved.is_empty(),
        "allDependencies": blocked_by,
    })))
}

/// POST /api/issues/{iid}/verify -- harness calls this after completing work.
pub async fn verify(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
    Json(body): Json<VerifyOutcomeRequest>,
) -> AppResult<Json<IssueOutcome>> {
    let issue = resolve_issue(&state, &iid).await?;

    let id = Uuid::new_v4().to_string();
    let verified_at = chrono::Utc::now().to_rfc3339();

    let tests_passed = body.tests_passed.unwrap_or(0);
    let tests_failed = body.tests_failed.unwrap_or(0);
    let tests_before = body.tests_before.unwrap_or(0);
    let tests_after = body.tests_after.unwrap_or(0);
    let files_changed = serde_json::to_string(&body.files_changed.unwrap_or_default())
        .unwrap_or_else(|_| "[]".to_string());
    let files_added = serde_json::to_string(&body.files_added.unwrap_or_default())
        .unwrap_or_else(|_| "[]".to_string());
    let files_removed = serde_json::to_string(&body.files_removed.unwrap_or_default())
        .unwrap_or_else(|_| "[]".to_string());
    let import_errors = serde_json::to_string(&body.import_errors.unwrap_or_default())
        .unwrap_or_else(|_| "[]".to_string());
    let build_success = body.build_success.unwrap_or(false);
    let success = body.success.unwrap_or(false);
    let summary = body.summary.unwrap_or_default();
    let raw_output = body.raw_output;
    let duration_ms = body.duration_ms.unwrap_or(0);

    sqlx::query(
        "INSERT INTO issue_outcomes (id, issue_id, verified_at, tests_passed, tests_failed,
         tests_before, tests_after, files_changed, files_added, files_removed, import_errors,
         build_success, success, summary, raw_output, duration_ms)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&issue.id)
        .bind(&verified_at)
        .bind(tests_passed)
        .bind(tests_failed)
        .bind(tests_before)
        .bind(tests_after)
        .bind(&files_changed)
        .bind(&files_added)
        .bind(&files_removed)
        .bind(&import_errors)
        .bind(build_success)
        .bind(success)
        .bind(&summary)
        .bind(&raw_output)
        .bind(duration_ms)
        .execute(&state.pool)
        .await?;

    // Log warnings for failures
    if tests_failed > 0 || !build_success {
        tracing::warn!(
            issue_id = %issue.id,
            identifier = %issue.identifier.as_deref().unwrap_or("unknown"),
            tests_failed,
            build_success,
            "Outcome verification: issue has failures"
        );
    }

    let outcome = query_as::<_, IssueOutcome>("SELECT * FROM issue_outcomes WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;

    log_activity(&state, &issue.company_id, "agent", "harness", "issue.verified", "issue", &issue.id,
        Some(serde_json::json!({
            "outcome_id": id,
            "success": success,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
        }).to_string())
    ).await;

    Ok(Json(outcome))
}

/// GET /api/issues/{iid}/outcomes -- all outcome records for an issue.
pub async fn list_outcomes(
    State(state): State<SharedState>,
    Path(iid): Path<String>,
) -> AppResult<Json<Vec<IssueOutcome>>> {
    let issue = resolve_issue(&state, &iid).await?;
    let outcomes = query_as::<_, IssueOutcome>(
        "SELECT * FROM issue_outcomes WHERE issue_id = ? ORDER BY created_at DESC"
    )
        .bind(&issue.id)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(outcomes))
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
    let Some(ident) = identifier.as_deref() else { return; };

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

        // P0-3 fix: Query the DB to verify ALL deps are actually in done/cancelled status.
        // The old code only checked if dep == ident (the just-completed issue), which
        // breaks multi-dep chains where other blockers haven't been resolved yet.
        let all_resolved = are_all_deps_resolved(state, company_id, &deps).await;

        if all_resolved {
            // Auto-promote to todo
            let _ = sqlx::query(
                "UPDATE issues SET status = 'todo', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(&issue.id)
                .execute(&state.pool)
                .await;

            tracing::info!("Auto-promoted {} to todo (all blockers resolved)", issue.identifier.clone().unwrap_or_default());

            log_activity(state, company_id, "system", "geo-forge", "issue.auto_promoted", "issue", &issue.id,
                Some(serde_json::json!({
                    "from": "backlog",
                    "to": "todo",
                    "reason": "all blockers resolved",
                    "identifier": issue.identifier
                }).to_string())
            ).await;
        }
    }
}

/// Check if all dependency identifiers are resolved (done or cancelled).
async fn are_all_deps_resolved(state: &SharedState, company_id: &str, deps: &[String]) -> bool {
    if deps.is_empty() {
        return true;
    }

    for dep in deps {
        // Look up each dependency by identifier in the same company
        let issue = query_as::<_, Issue>(
            "SELECT * FROM issues WHERE company_id = ? AND identifier = ?"
        )
            .bind(company_id)
            .bind(dep)
            .fetch_optional(&state.pool)
            .await;

        match issue {
            Ok(Some(i)) => {
                if i.status != "done" && i.status != "cancelled" {
                    return false;
                }
            }
            Ok(None) => {
                // Unknown dependency -- treat as unresolved to be safe
                tracing::warn!("Unknown dependency '{}' referenced in blocked_by", dep);
                return false;
            }
            Err(e) => {
                tracing::error!("Error checking dependency '{}': {}", dep, e);
                return false;
            }
        }
    }
    true
}

/// Validate that all identifiers in blocked_by exist as issues in the same company.
async fn validate_blocked_by(
    state: &SharedState,
    company_id: &str,
    deps: &[String],
) -> Result<(), crate::error::AppError> {
    if deps.is_empty() {
        return Ok(());
    }
    for dep in deps {
        let exists = query_as::<_, Issue>(
            "SELECT * FROM issues WHERE company_id = ? AND identifier = ?"
        )
            .bind(company_id)
            .bind(dep)
            .fetch_optional(&state.pool)
            .await
            .map_err(|e| crate::error::AppError::Internal(e.to_string()))?;

        if exists.is_none() {
            return Err(crate::error::AppError::Validation(format!(
                "Unknown dependency '{}' -- no issue with that identifier exists in this company",
                dep
            )));
        }
    }
    Ok(())
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
