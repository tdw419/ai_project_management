use axum::{extract::{Path, State}, response::Json};
use serde_json::{json, Value};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{SpecDocument, SpecIssue, ParsedChange, CreateSpecRequest, ImportSpecRequest};
use crate::db::models::{Issue, Company};

// ============================================================
// CRUD
// ============================================================

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<SpecDocument>>> {
    let specs = query_as::<_, SpecDocument>(
        "SELECT * FROM spec_documents WHERE company_id = ? ORDER BY created_at DESC"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(specs))
}

pub async fn get(
    State(state): State<SharedState>,
    Path(sid): Path<String>,
) -> AppResult<Json<SpecDocument>> {
    let spec = resolve_spec(&state, &sid).await?;
    Ok(Json(spec))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateSpecRequest>,
) -> AppResult<Json<SpecDocument>> {
    crate::validation::require_non_empty(&body.title, "title")?;
    crate::validation::validate_length(&body.title, "title", crate::validation::MAX_TITLE_LEN)?;
    crate::validation::validate_length(&body.raw_content, "raw_content", crate::validation::MAX_SPEC_CONTENT_LEN)?;

    // Parse the raw content into change sections
    let changes = parse_openspec(&body.raw_content)?;

    let id = Uuid::new_v4().to_string();
    let change_count = changes.len() as i64;
    let parsed_json = serde_json::to_string(&changes)
        .map_err(|e| AppError::Internal(format!("Failed to serialize parsed changes: {}", e)))?;

    sqlx::query(
        "INSERT INTO spec_documents (id, company_id, title, raw_content, parsed_changes, change_count, project_id)
         VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.title)
        .bind(&body.raw_content)
        .bind(&parsed_json)
        .bind(change_count)
        .bind(&body.project_id)
        .execute(&state.pool)
        .await?;

    let spec = query_as::<_, SpecDocument>("SELECT * FROM spec_documents WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;

    log_activity(&state, &cid, "system", "geo-forge", "spec.created", "spec_document", &id,
        Some(json!({"title": body.title, "changeCount": change_count}).to_string())
    ).await;

    Ok(Json(spec))
}

pub async fn delete(
    State(state): State<SharedState>,
    Path(sid): Path<String>,
) -> AppResult<Json<Value>> {
    let spec = resolve_spec(&state, &sid).await?;

    // Delete spec_issues mappings first
    sqlx::query("DELETE FROM spec_issues WHERE spec_id = ?")
        .bind(&spec.id)
        .execute(&state.pool)
        .await?;

    sqlx::query("DELETE FROM spec_documents WHERE id = ?")
        .bind(&spec.id)
        .execute(&state.pool)
        .await?;

    log_activity(&state, &spec.company_id, "system", "geo-forge", "spec.deleted", "spec_document", &spec.id, None).await;

    Ok(Json(json!({"deleted": true, "id": spec.id})))
}

// ============================================================
// Import: convert parsed changes to issues
// ============================================================

pub async fn import(
    State(state): State<SharedState>,
    Path(sid): Path<String>,
    Json(body): Json<ImportSpecRequest>,
) -> AppResult<Json<Value>> {
    let spec = resolve_spec(&state, &sid).await?;

    if spec.status == "imported" {
        return Err(AppError::Validation(format!(
            "Spec {} has already been fully imported", spec.id
        )));
    }

    let changes: Vec<ParsedChange> = serde_json::from_str(&spec.parsed_changes)
        .map_err(|e| AppError::Internal(format!("Failed to parse stored changes: {}", e)))?;

    if changes.is_empty() {
        return Err(AppError::Validation("Spec has no change sections to import".into()));
    }

    // Determine which indices to import
    let indices: Vec<usize> = match &body.indices {
        Some(idx) if !idx.is_empty() => {
            // Validate indices are in range
            for &i in idx {
                if i < 0 || (i as usize) >= changes.len() {
                    return Err(AppError::Validation(format!(
                        "Change index {} out of range (0..{})", i, changes.len()
                    )));
                }
            }
            idx.iter().map(|&i| i as usize).collect()
        }
        _ => (0..changes.len()).collect(),
    };

    // Get company for issue prefix/counter
    let company = query_as::<_, Company>("SELECT * FROM companies WHERE id = ?")
        .bind(&spec.company_id)
        .fetch_one(&state.pool)
        .await?;

    let mut imported: Vec<Value> = Vec::new();

    for idx in &indices {
        let change = &changes[*idx];

        // Skip if already imported (check spec_issues for this change_index)
        let existing: Option<(String,)> = sqlx::query_as(
            "SELECT issue_id FROM spec_issues WHERE spec_id = ? AND change_index = ?"
        )
            .bind(&spec.id)
            .bind(*idx as i64)
            .fetch_optional(&state.pool)
            .await
            .map_err(|e| AppError::Internal(e.to_string()))?;

        if existing.is_some() {
            // Already imported this change, skip
            continue;
        }

        // Create the issue (same pattern as issues::create)
        let issue_id = Uuid::new_v4().to_string();

        let counter: (i64,) = sqlx::query_as(
            "UPDATE companies SET issue_counter = issue_counter + 1, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ? RETURNING issue_counter"
        )
            .bind(&spec.company_id)
            .fetch_one(&state.pool)
            .await?;

        let issue_number = counter.0;
        let identifier = format!("{}-{}", company.issue_prefix, issue_number);

        // Validate blocked_by identifiers
        if !change.blocked_by.is_empty() {
            validate_blocked_by(&state, &spec.company_id, &change.blocked_by).await?;
        }

        let has_blockers = !change.blocked_by.is_empty();
        let blocked_by_json = serde_json::to_string(&change.blocked_by)
            .unwrap_or_else(|_| "[]".to_string());
        let initial_status = if has_blockers { "backlog" } else { "todo" };

        sqlx::query(
            "INSERT INTO issues (id, company_id, project_id, title, description, status, priority,
             identifier, issue_number, origin_kind, origin_id, blocked_by)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'spec', ?, ?)"
        )
            .bind(&issue_id)
            .bind(&spec.company_id)
            .bind(&spec.project_id)
            .bind(&change.title)
            .bind(&change.description)
            .bind(&initial_status)
            .bind(&change.priority)
            .bind(&identifier)
            .bind(issue_number)
            .bind(&spec.id)
            .bind(&blocked_by_json)
            .execute(&state.pool)
            .await?;

        // Create spec_issues mapping
        let mapping_id = Uuid::new_v4().to_string();
        sqlx::query(
            "INSERT INTO spec_issues (id, spec_id, issue_id, change_index, change_title) VALUES (?, ?, ?, ?, ?)"
        )
            .bind(&mapping_id)
            .bind(&spec.id)
            .bind(&issue_id)
            .bind(*idx as i64)
            .bind(&change.title)
            .execute(&state.pool)
            .await?;

        log_activity(&state, &spec.company_id, "system", "geo-forge", "issue.created", "issue", &issue_id,
            Some(json!({"origin": "spec_import", "specId": spec.id, "changeIndex": *idx}).to_string())
        ).await;

        imported.push(json!({
            "changeIndex": *idx,
            "issueId": issue_id,
            "identifier": identifier,
            "title": change.title,
            "status": initial_status,
        }));
    }

    // Update spec status and imported_count
    let total_imported: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM spec_issues WHERE spec_id = ?"
    )
        .bind(&spec.id)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    let new_status = if total_imported.0 as usize >= changes.len() { "imported" } else { "partial" };

    sqlx::query(
        "UPDATE spec_documents SET status = ?, imported_count = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&new_status)
        .bind(total_imported.0)
        .bind(&spec.id)
        .execute(&state.pool)
        .await?;

    log_activity(&state, &spec.company_id, "system", "geo-forge", "spec.imported", "spec_document", &spec.id,
        Some(json!({"importedCount": imported.len(), "status": new_status}).to_string())
    ).await;

    Ok(Json(json!({
        "specId": spec.id,
        "imported": imported.len(),
        "status": new_status,
        "issues": imported,
    })))
}

/// Get all issues created from a spec document.
pub async fn spec_issues(
    State(state): State<SharedState>,
    Path(sid): Path<String>,
) -> AppResult<Json<Value>> {
    let spec = resolve_spec(&state, &sid).await?;

    let mappings = query_as::<_, SpecIssue>(
        "SELECT * FROM spec_issues WHERE spec_id = ? ORDER BY change_index"
    )
        .bind(&spec.id)
        .fetch_all(&state.pool)
        .await?;

    let mut results = Vec::new();
    for m in &mappings {
        let issue = query_as::<_, Issue>("SELECT * FROM issues WHERE id = ?")
            .bind(&m.issue_id)
            .fetch_optional(&state.pool)
            .await?;
        results.push(json!({
            "mapping": m,
            "issue": issue,
        }));
    }

    Ok(Json(json!({
        "specId": spec.id,
        "total": results.len(),
        "items": results,
    })))
}

// ============================================================
// OpenSpec Parser
// ============================================================

/// Parse an OpenSpec document into change sections.
///
/// Format (text, not code):
///
///   # Spec: <spec title>
///   ## Change: <change title>
///   priority: <low|medium|high|critical>
///   blocked_by: [IDENTIFIER-1, IDENTIFIER-2]
///   description: <optional single-line description>
///   <multi-line body text>
///   ---
///   ## Change: <next change>
///   ...
pub fn parse_openspec(raw: &str) -> Result<Vec<ParsedChange>, AppError> {
    let mut changes: Vec<ParsedChange> = Vec::new();
    let mut current: Option<ParsedChange> = None;
    let mut body_lines: Vec<String> = Vec::new();

    for line in raw.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("## Change:") || trimmed.starts_with("## change:") {
            // Flush previous change
            if let Some(mut c) = current.take() {
                if !body_lines.is_empty() {
                    let body = body_lines.join("\n").trim().to_string();
                    if c.description.is_empty() {
                        c.description = body;
                    } else {
                        c.description = format!("{}\n\n{}", c.description, body);
                    }
                }
                changes.push(c);
                body_lines.clear();
            }

            let title = trimmed
                .trim_start_matches("## Change:")
                .trim_start_matches("## change:")
                .trim()
                .to_string();

            current = Some(ParsedChange {
                title,
                priority: "medium".to_string(),
                blocked_by: Vec::new(),
                description: String::new(),
            });
            continue;
        }

        // Only parse metadata/body if we're inside a change section
        let c = match &mut current {
            Some(c) => c,
            None => continue,
        };

        if trimmed.starts_with("priority:") {
            let val = trimmed.trim_start_matches("priority:").trim().to_lowercase();
            c.priority = match val.as_str() {
                "low" | "medium" | "high" | "critical" => val,
                _ => "medium".to_string(),
            };
        } else if trimmed.starts_with("blocked_by:") {
            let val = trimmed.trim_start_matches("blocked_by:").trim();
            if val.starts_with('[') && val.ends_with(']') {
                let inner = &val[1..val.len()-1];
                c.blocked_by = inner
                    .split(',')
                    .map(|s| s.trim().trim_matches('"').trim_matches('\'').to_string())
                    .filter(|s| !s.is_empty())
                    .collect();
            }
        } else if trimmed.starts_with("description:") {
            let desc = trimmed.trim_start_matches("description:").trim().to_string();
            c.description = desc;
        } else if trimmed == "---" {
            // Section separator -- flush current change
            if let Some(mut c) = current.take() {
                if !body_lines.is_empty() {
                    let body = body_lines.join("\n").trim().to_string();
                    if c.description.is_empty() {
                        c.description = body;
                    } else {
                        c.description = format!("{}\n\n{}", c.description, body);
                    }
                }
                changes.push(c);
                body_lines.clear();
            }
        } else if !trimmed.is_empty() {
            // Regular text goes to body
            body_lines.push(line.to_string());
        }
    }

    // Flush last change
    if let Some(mut c) = current {
        if !body_lines.is_empty() {
            let body = body_lines.join("\n").trim().to_string();
            if c.description.is_empty() {
                c.description = body;
            } else {
                c.description = format!("{}\n\n{}", c.description, body);
            }
        }
        changes.push(c);
    }

    Ok(changes)
}

// ============================================================
// Helpers
// ============================================================

async fn resolve_spec(state: &SharedState, sid: &str) -> AppResult<SpecDocument> {
    query_as::<_, SpecDocument>("SELECT * FROM spec_documents WHERE id = ?")
        .bind(sid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Spec document {} not found", sid)))
}

/// Validate that all identifiers in blocked_by exist as issues in the same company.
async fn validate_blocked_by(
    state: &SharedState,
    company_id: &str,
    deps: &[String],
) -> Result<(), AppError> {
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
            .map_err(|e| AppError::Internal(e.to_string()))?;

        if exists.is_none() {
            return Err(AppError::Validation(format!(
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
