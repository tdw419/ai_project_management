use axum::{extract::{Path, State}, response::Json};
use serde_json::{json, Value};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppResult, SharedState};
use crate::db::models::{Company, AgentSummary, TaskSummary, CreateCompanyRequest};

pub async fn list(State(state): State<SharedState>) -> AppResult<Json<Vec<Company>>> {
    let companies = query_as::<_, Company>("SELECT * FROM companies ORDER BY created_at")
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(companies))
}

pub async fn create(
    State(state): State<SharedState>,
    Json(body): Json<CreateCompanyRequest>,
) -> AppResult<Json<Company>> {
    let id = Uuid::new_v4().to_string();
    let issue_prefix = body.issue_prefix.unwrap_or_else(|| "GEO".to_string());
    let qa_gate = body.qa_gate.unwrap_or(true);

    sqlx::query(
        "INSERT INTO companies (id, name, description, issue_prefix, qa_gate) VALUES (?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&body.name)
        .bind(&body.description)
        .bind(&issue_prefix)
        .bind(qa_gate)
        .execute(&state.pool)
        .await?;

    let company = query_as::<_, Company>("SELECT * FROM companies WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(company))
}

pub async fn get(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Company>> {
    let company = query_as::<_, Company>("SELECT * FROM companies WHERE id = ?")
        .bind(&cid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| crate::error::AppError::NotFound(format!("Company {} not found", cid)))?;
    Ok(Json(company))
}

pub async fn dashboard(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Value>> {
    // Agent summary
    let agent_counts: Vec<(String, i64)> = sqlx::query_as(
        "SELECT status, COUNT(*) as cnt FROM agents WHERE company_id = ? GROUP BY status"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;

    let mut agents = AgentSummary { active: 0, idle: 0, paused: 0, error: 0 };
    for (status, count) in agent_counts {
        match status.as_str() {
            "running" => agents.active = count,
            "idle" => agents.idle = count,
            "paused" => agents.paused = count,
            "error" => agents.error = count,
            _ => {}
        }
    }

    // Task summary
    let task_counts: Vec<(String, i64)> = sqlx::query_as(
        "SELECT status, COUNT(*) as cnt FROM issues WHERE company_id = ? GROUP BY status"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;

    let mut tasks = TaskSummary {
        backlog: 0, todo: 0, in_progress: 0, in_review: 0, done: 0, cancelled: 0,
    };
    for (status, count) in task_counts {
        match status.as_str() {
            "backlog" => tasks.backlog = count,
            "todo" => tasks.todo = count,
            "in_progress" => tasks.in_progress = count,
            "in_review" => tasks.in_review = count,
            "done" => tasks.done = count,
            "cancelled" => tasks.cancelled = count,
            _ => {}
        }
    }

    Ok(Json(json!({
        "companyId": cid,
        "agents": agents,
        "tasks": tasks,
    })))
}
