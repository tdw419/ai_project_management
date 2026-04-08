use axum::{extract::{Path, Query, State}, response::Json};
use serde_json;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{
    Event, Webhook, WebhookDelivery,
    CreateWebhookRequest, UpdateWebhookRequest, ListEventsParams,
};
// -- Webhook CRUD --

pub async fn list_webhooks(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<Webhook>>> {
    let webhooks = sqlx::query_as::<_, Webhook>(
        "SELECT * FROM webhooks WHERE company_id = ? ORDER BY created_at DESC"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(webhooks))
}

pub async fn create_webhook(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateWebhookRequest>,
) -> AppResult<Json<Webhook>> {
    crate::validation::require_non_empty(&body.event_type, "event_type")?;
    crate::validation::require_non_empty(&body.target_url, "target_url")?;

    // Verify company exists
    sqlx::query_as::<_, crate::db::models::Company>(
        "SELECT * FROM companies WHERE id = ?"
    )
        .bind(&cid)
        .fetch_one(&state.pool)
        .await?;

    let id = Uuid::new_v4().to_string();
    let secret = body.secret.unwrap_or_else(|| {
        // Generate a random secret if not provided
        format!("{:x}", Uuid::new_v4())
    });
    let headers = body.headers
        .map(|h| serde_json::to_string(&h).unwrap_or_else(|_| "{}".to_string()))
        .unwrap_or_else(|| "{}".to_string());
    let now = chrono::Utc::now().to_rfc3339();

    sqlx::query(
        "INSERT INTO webhooks (id, company_id, event_type, target_url, secret, active, headers, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.event_type)
        .bind(&body.target_url)
        .bind(&secret)
        .bind(&headers)
        .bind(&now)
        .bind(&now)
        .execute(&state.pool)
        .await?;

    let webhook = sqlx::query_as::<_, Webhook>(
        "SELECT * FROM webhooks WHERE id = ?"
    )
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;

    tracing::info!(webhook_id = %id, company_id = %cid, event_type = %body.event_type, "Webhook created");

    Ok(Json(webhook))
}

pub async fn update_webhook(
    State(state): State<SharedState>,
    Path(wid): Path<String>,
    Json(body): Json<UpdateWebhookRequest>,
) -> AppResult<Json<Webhook>> {
    let webhook = sqlx::query_as::<_, Webhook>(
        "SELECT * FROM webhooks WHERE id = ?"
    )
        .bind(&wid)
        .fetch_one(&state.pool)
        .await
        .map_err(|_| AppError::NotFound(format!("Webhook {} not found", wid)))?;

    let event_type = body.event_type.unwrap_or(webhook.event_type);
    let target_url = body.target_url.unwrap_or(webhook.target_url);
    let active = body.active.unwrap_or(webhook.active);
    let headers = body.headers
        .map(|h| serde_json::to_string(&h).unwrap_or_else(|_| "{}".to_string()))
        .unwrap_or(webhook.headers);

    let now = chrono::Utc::now().to_rfc3339();

    sqlx::query(
        "UPDATE webhooks SET event_type = ?, target_url = ?, active = ?, headers = ?, updated_at = ?
         WHERE id = ?"
    )
        .bind(&event_type)
        .bind(&target_url)
        .bind(active)
        .bind(&headers)
        .bind(&now)
        .bind(&wid)
        .execute(&state.pool)
        .await?;

    let updated = sqlx::query_as::<_, Webhook>(
        "SELECT * FROM webhooks WHERE id = ?"
    )
        .bind(&wid)
        .fetch_one(&state.pool)
        .await?;

    Ok(Json(updated))
}

pub async fn delete_webhook(
    State(state): State<SharedState>,
    Path(wid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let result = sqlx::query("DELETE FROM webhooks WHERE id = ?")
        .bind(&wid)
        .execute(&state.pool)
        .await?;

    if result.rows_affected() == 0 {
        return Err(AppError::NotFound(format!("Webhook {} not found", wid)));
    }

    Ok(Json(serde_json::json!({"deleted": wid})))
}

// -- Events --

pub async fn list_events(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Query(params): Query<ListEventsParams>,
) -> AppResult<Json<Vec<Event>>> {
    let mut sql = String::from("SELECT * FROM events WHERE company_id = ?");
    let mut bindings: Vec<String> = vec![cid.clone()];

    if let Some(ref event_type) = params.event_type {
        sql.push_str(" AND event_type = ?");
        bindings.push(event_type.clone());
    }
    if let Some(ref since) = params.since {
        sql.push_str(" AND created_at >= ?");
        bindings.push(since.clone());
    }

    sql.push_str(" ORDER BY created_at DESC");

    let limit = params.limit.unwrap_or(100).min(500);
    let offset = params.offset.unwrap_or(0);
    sql.push_str(" LIMIT ? OFFSET ?");
    bindings.push(limit.to_string());
    bindings.push(offset.to_string());

    let mut query = sqlx::query_as::<_, Event>(&sql);
    for b in &bindings {
        query = query.bind(b);
    }

    let events = query.fetch_all(&state.pool).await?;
    Ok(Json(events))
}

// -- Deliveries --

pub async fn list_deliveries(
    State(state): State<SharedState>,
    Path(wid): Path<String>,
) -> AppResult<Json<Vec<WebhookDelivery>>> {
    let deliveries = sqlx::query_as::<_, WebhookDelivery>(
        "SELECT * FROM webhook_deliveries WHERE webhook_id = ? ORDER BY created_at DESC LIMIT 50"
    )
        .bind(&wid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(deliveries))
}

/// Redeliver a specific delivery attempt.
pub async fn redeliver(
    State(state): State<SharedState>,
    Path(did): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let _delivery = sqlx::query_as::<_, WebhookDelivery>(
        "SELECT * FROM webhook_deliveries WHERE id = ?"
    )
        .bind(&did)
        .fetch_one(&state.pool)
        .await
        .map_err(|_| AppError::NotFound(format!("Delivery {} not found", did)))?;

    // Reset the delivery for retry
    sqlx::query(
        "UPDATE webhook_deliveries SET status = 'pending', attempts = 0, next_retry_at = NULL
         WHERE id = ?"
    )
        .bind(&did)
        .execute(&state.pool)
        .await?;

    Ok(Json(serde_json::json!({
        "id": did,
        "status": "pending",
        "message": "Delivery queued for retry"
    })))
}

/// Ping a webhook to test connectivity.
pub async fn ping(
    State(state): State<SharedState>,
    Path(wid): Path<String>,
) -> AppResult<Json<serde_json::Value>> {
    let webhook = sqlx::query_as::<_, Webhook>(
        "SELECT * FROM webhooks WHERE id = ?"
    )
        .bind(&wid)
        .fetch_one(&state.pool)
        .await
        .map_err(|_| AppError::NotFound(format!("Webhook {} not found", wid)))?;

    let now = chrono::Utc::now().to_rfc3339();
    let ping_payload = serde_json::json!({
        "event_type": "webhook.ping",
        "webhook_id": &webhook.id,
        "data": {"message": "ping from geo-forge"},
        "timestamp": now,
    });
    let payload_str = ping_payload.to_string();

    let event_id = Uuid::new_v4().to_string();
    let delivery_id = Uuid::new_v4().to_string();

    sqlx::query(
        "INSERT INTO webhook_deliveries (id, webhook_id, event_id, payload, status, attempts, max_attempts, created_at)
         VALUES (?, ?, ?, ?, 'pending', 0, 1, ?)"
    )
        .bind(&delivery_id)
        .bind(&webhook.id)
        .bind(&event_id)
        .bind(&payload_str)
        .bind(&now)
        .execute(&state.pool)
        .await?;

    Ok(Json(serde_json::json!({
        "delivery_id": delivery_id,
        "message": "Ping delivery queued"
    })))
}
