use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::Agent;

/// Generic dispatch: find an idle agent and assign the highest-priority todo issue.
/// This is what Paperclip couldn't do -- it required one routine per agent.
pub async fn dispatch(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<crate::db::models::DispatchRequest>,
) -> AppResult<Json<serde_json::Value>> {
    // Find an idle agent (optionally matching a role)
    let agent = if let Some(ref agent_id) = body.agent_id {
        // Specific agent requested
        query_as::<_, Agent>("SELECT * FROM agents WHERE id = ? AND company_id = ?")
            .bind(agent_id)
            .bind(&cid)
            .fetch_optional(&state.pool)
            .await?
            .ok_or_else(|| AppError::NotFound(format!("Agent {} not found in company", agent_id)))?
    } else {
        // Find an idle agent matching the role (or any idle agent)
        let role_filter = body.role.as_deref().unwrap_or("engineer");
        query_as::<_, Agent>(
            "SELECT * FROM agents WHERE company_id = ? AND status = 'idle' AND role = ? LIMIT 1"
        )
            .bind(&cid)
            .bind(role_filter)
            .fetch_optional(&state.pool)
            .await?
            .ok_or_else(|| AppError::NotFound(format!("No idle {} agents available", role_filter)))?
    };

    // Find the highest-priority unassigned todo issue
    let issue = if let Some(ref issue_id) = body.issue_id {
        // Specific issue requested
        sqlx::query_as::<_, crate::db::models::Issue>(
            "SELECT * FROM issues WHERE id = ? AND company_id = ? AND status = 'todo'"
        )
            .bind(issue_id)
            .bind(&cid)
            .fetch_optional(&state.pool)
            .await?
            .ok_or_else(|| AppError::NotFound(format!("Issue {} not found or not in todo", issue_id)))?
    } else {
        // Auto-pick: highest priority, oldest first
        let priority_order = "CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 WHEN 'low' THEN 4 END";
        sqlx::query_as::<_, crate::db::models::Issue>(
            &format!("SELECT * FROM issues WHERE company_id = ? AND status = 'todo' AND (assignee_agent_id IS NULL OR assignee_agent_id = ?) ORDER BY {} ASC, created_at ASC LIMIT 1", priority_order)
        )
            .bind(&cid)
            .bind(&agent.id)
            .fetch_optional(&state.pool)
            .await?
            .ok_or_else(|| AppError::NotFound("No unassigned todo issues available".to_string()))?
    };

    // Checkout the issue to the agent
    let now = chrono::Utc::now().to_rfc3339();
    sqlx::query(
        "UPDATE issues SET status = 'in_progress', assignee_agent_id = ?,
         started_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&agent.id)
        .bind(&now)
        .bind(&issue.id)
        .execute(&state.pool)
        .await?;

    tracing::info!(
        "Dispatched issue {} to agent {} ({})",
        issue.identifier.as_deref().unwrap_or(&issue.id),
        agent.name,
        agent.id,
    );

    // Determine effective strategy: if issue has prior failed outcomes, pivot
    let outcome_count: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM issue_outcomes WHERE issue_id = ? AND success = 0"
    )
        .bind(&issue.id)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    let effective_strategy = if outcome_count.0 > 0 {
        // Prior failures exist -- pivot strategy
        let pivoted = crate::db::models::pivot_strategy(issue.strategy.as_deref());
        // Update issue with pivoted strategy
        sqlx::query("UPDATE issues SET strategy = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?")
            .bind(&pivoted)
            .bind(&issue.id)
            .execute(&state.pool)
            .await?;
        pivoted
    } else {
        issue.strategy.clone().unwrap_or_else(|| "surgeon".to_string())
    };

    // Fetch prompt template for the strategy
    let prompt_template = sqlx::query_as::<_, crate::db::models::PromptTemplate>(
        "SELECT * FROM prompt_templates WHERE strategy = ?"
    )
        .bind(&effective_strategy)
        .fetch_optional(&state.pool)
        .await
        .ok()
        .flatten();

    // P11-C: Inject relevant learnings into dispatch response
    let learnings = crate::routes::learnings::get_learnings_for_dispatch(&state, &cid, &issue).await;

    Ok(Json(serde_json::json!({
        "dispatched": true,
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
        },
        "issue": {
            "id": issue.id,
            "identifier": issue.identifier,
            "title": issue.title,
        },
        "strategy": effective_strategy,
        "strategyPivoted": outcome_count.0 > 0,
        "prompt": prompt_template.map(|t| t.prompt).unwrap_or_default(),
        "priorAttempts": outcome_count.0,
        "learnings": learnings,
    })))
}
