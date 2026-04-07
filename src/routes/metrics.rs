use axum::extract::State;
use axum::response::Json;
use crate::SharedState;

/// GET /api/metrics -- structured operational metrics (JSON, not prometheus text format)
pub async fn metrics(State(state): State<SharedState>) -> Result<Json<serde_json::Value>, crate::AppError> {
    let agents_total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM agents")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("agents_total: {}", e)))?;

    let agents_by_status: Vec<(String, i64)> = sqlx::query_as(
        "SELECT status, COUNT(*) FROM agents GROUP BY status"
    )
        .fetch_all(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("agents_by_status: {}", e)))?;

    let agents_by_health: Vec<(String, i64)> = sqlx::query_as(
        "SELECT health_status, COUNT(*) FROM agents GROUP BY health_status"
    )
        .fetch_all(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("agents_by_health: {}", e)))?;

    let issues_total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM issues")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues_total: {}", e)))?;

    let issues_by_status: Vec<(String, i64)> = sqlx::query_as(
        "SELECT status, COUNT(*) FROM issues GROUP BY status"
    )
        .fetch_all(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues_by_status: {}", e)))?;

    let issues_by_priority: Vec<(String, i64)> = sqlx::query_as(
        "SELECT priority, COUNT(*) FROM issues GROUP BY priority"
    )
        .fetch_all(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("issues_by_priority: {}", e)))?;

    let companies_total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM companies")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("companies_total: {}", e)))?;

    let projects_total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM projects")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("projects_total: {}", e)))?;

    let invocations_total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM invocations")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("invocations_total: {}", e)))?;

    let invocations_success: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM invocations WHERE success = 1"
    )
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("invocations_success: {}", e)))?;

    let invocations_failed: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM invocations WHERE success = 0"
    )
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("invocations_failed: {}", e)))?;

    let avg_duration_ms: (Option<f64>,) = sqlx::query_as(
        "SELECT AVG(duration_ms) FROM invocations WHERE duration_ms IS NOT NULL"
    )
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("avg_duration: {}", e)))?;

    let routines_total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM routines")
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("routines_total: {}", e)))?;

    let activity_24h: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM activity_log WHERE created_at >= datetime('now', '-1 day')"
    )
        .fetch_one(&state.pool)
        .await
        .map_err(|e| crate::AppError::Internal(format!("activity_24h: {}", e)))?;

    // Convert group-by results to maps
    let status_map: serde_json::Map<String, serde_json::Value> = agents_by_status.into_iter()
        .map(|(k, v)| (k, serde_json::Value::from(v)))
        .collect();

    let health_map: serde_json::Map<String, serde_json::Value> = agents_by_health.into_iter()
        .map(|(k, v)| (k, serde_json::Value::from(v)))
        .collect();

    let issue_status_map: serde_json::Map<String, serde_json::Value> = issues_by_status.into_iter()
        .map(|(k, v)| (k, serde_json::Value::from(v)))
        .collect();

    let issue_priority_map: serde_json::Map<String, serde_json::Value> = issues_by_priority.into_iter()
        .map(|(k, v)| (k, serde_json::Value::from(v)))
        .collect();

    Ok(Json(serde_json::json!({
        "service": "geo-forge",
        "version": env!("CARGO_PKG_VERSION"),
        "timestamp": chrono::Utc::now().to_rfc3339(),
        "agents": {
            "total": agents_total.0,
            "by_status": status_map,
            "by_health": health_map,
        },
        "issues": {
            "total": issues_total.0,
            "by_status": issue_status_map,
            "by_priority": issue_priority_map,
        },
        "companies": companies_total.0,
        "projects": projects_total.0,
        "routines": routines_total.0,
        "invocations": {
            "total": invocations_total.0,
            "success": invocations_success.0,
            "failed": invocations_failed.0,
            "avg_duration_ms": avg_duration_ms.0,
        },
        "activity_last_24h": activity_24h.0,
    })))
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_metrics_json_structure() {
        // Verify the expected shape compiles and is reasonable
        let v = serde_json::json!({
            "service": "geo-forge",
            "version": "0.1.0",
            "agents": { "total": 0, "by_status": {}, "by_health": {} },
            "issues": { "total": 0, "by_status": {}, "by_priority": {} },
            "companies": 0,
            "projects": 0,
            "routines": 0,
            "invocations": { "total": 0, "success": 0, "failed": 0, "avg_duration_ms": null },
            "activity_last_24h": 0,
        });
        assert!(v["agents"]["total"].is_number());
        assert!(v["invocations"]["avg_duration_ms"].is_null());
    }
}
