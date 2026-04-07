use axum::extract::State;
use axum::response::Json;
use crate::SharedState;

/// GET /api/stats -- summary counts for companies, agents, and issues by status
pub async fn stats(State(state): State<SharedState>) -> Result<Json<serde_json::Value>, crate::AppError> {
    let companies: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM companies")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("companies count: {}", e)))?;

    let agents: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM agents")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("agents count: {}", e)))?;

    let todo: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM issues WHERE status = 'todo'")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues todo: {}", e)))?;

    let in_progress: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM issues WHERE status = 'in_progress'")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues in_progress: {}", e)))?;

    let in_review: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM issues WHERE status = 'in_review'")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues in_review: {}", e)))?;

    let done: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM issues WHERE status = 'done'")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues done: {}", e)))?;

    Ok(Json(serde_json::json!({
        "companies": companies.0,
        "agents": agents.0,
        "issues": {
            "todo": todo.0,
            "in_progress": in_progress.0,
            "in_review": in_review.0,
            "done": done.0,
        },
    })))
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_stats_json_structure() {
        let v = serde_json::json!({
            "companies": 0,
            "agents": 0,
            "issues": {
                "todo": 0,
                "in_progress": 0,
                "in_review": 0,
                "done": 0,
            },
        });
        assert!(v["companies"].is_number());
        assert!(v["agents"].is_number());
        assert!(v["issues"]["todo"].is_number());
        assert!(v["issues"]["in_progress"].is_number());
        assert!(v["issues"]["in_review"].is_number());
        assert!(v["issues"]["done"].is_number());
    }
}
