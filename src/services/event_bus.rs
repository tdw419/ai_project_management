use tokio::sync::mpsc;
use sqlx::SqlitePool;
use serde_json;
use uuid::Uuid;

use crate::db::models::{Webhook, WebhookDelivery, StateChangeEvent};

/// The event bus runs as a background task. Route handlers send events
/// through the sender half; the receiver half persists them and triggers
/// webhook deliveries.

#[derive(Debug, Clone)]
pub struct EventBus {
    tx: mpsc::UnboundedSender<EventMessage>,
}

#[derive(Debug, Clone)]
pub struct EventMessage {
    pub company_id: String,
    pub event_type: String,
    pub payload: serde_json::Value,
}

impl EventBus {
    /// Create a new event bus and spawn the background worker.
    /// Returns the bus handle for sending events.
    pub fn spawn(pool: SqlitePool) -> Self {
        let (tx, rx) = mpsc::unbounded_channel();
        let pool_clone = pool.clone();

        tokio::spawn(async move {
            event_worker(rx, pool_clone).await;
        });

        EventBus { tx }
    }

    /// Emit an event. Non-blocking -- drops into the channel and returns immediately.
    /// If the channel is full (shouldn't happen with unbounded), the event is logged and dropped.
    pub fn emit(&self, company_id: &str, event_type: &str, payload: serde_json::Value) {
        let msg = EventMessage {
            company_id: company_id.to_string(),
            event_type: event_type.to_string(),
            payload,
        };
        if let Err(e) = self.tx.send(msg) {
            tracing::error!(error = %e, "Event channel send failed -- event dropped");
        }
    }

    /// Convenience: emit a state change event (old_value -> new_value).
    pub fn emit_state_change(
        &self,
        company_id: &str,
        entity_type: &str,
        entity_id: &str,
        field: &str,
        old_value: Option<serde_json::Value>,
        new_value: Option<serde_json::Value>,
    ) {
        let event_type = format!("{}.{}_changed", entity_type, field);
        let payload = serde_json::to_value(StateChangeEvent {
            event_type: event_type.clone(),
            company_id: company_id.to_string(),
            entity_type: entity_type.to_string(),
            entity_id: entity_id.to_string(),
            old_value,
            new_value,
            timestamp: chrono::Utc::now().to_rfc3339(),
        })
        .unwrap_or(serde_json::Value::Null);

        self.emit(company_id, &event_type, payload);
    }
}

/// Background worker: receives events, persists them, triggers webhook deliveries.
async fn event_worker(mut rx: mpsc::UnboundedReceiver<EventMessage>, pool: SqlitePool) {
    tracing::info!("Event bus worker started");

    while let Some(msg) = rx.recv().await {
        if let Err(e) = process_event(&pool, &msg).await {
            tracing::error!(
                company_id = %msg.company_id,
                event_type = %msg.event_type,
                error = %e,
                "Failed to process event"
            );
        }
    }

    tracing::warn!("Event bus worker stopped");
}

async fn process_event(pool: &SqlitePool, msg: &EventMessage) -> Result<(), sqlx::Error> {
    let id = Uuid::new_v4().to_string();
    let payload_str = serde_json::to_string(&msg.payload).unwrap_or_else(|_| "{}".to_string());
    let now = chrono::Utc::now().to_rfc3339();

    // Persist the event
    sqlx::query(
        "INSERT INTO events (id, company_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&msg.company_id)
        .bind(&msg.event_type)
        .bind(&payload_str)
        .bind(&now)
        .execute(pool)
        .await?;

    tracing::debug!(event_id = %id, event_type = %msg.event_type, "Event persisted");

    // Find matching webhooks and create deliveries
    let webhooks = find_matching_webhooks(pool, &msg.company_id, &msg.event_type).await?;
    for webhook in webhooks {
        create_delivery(pool, &webhook, &id, &payload_str).await;
    }

    Ok(())
}

/// Find active webhooks whose event_type pattern matches.
/// Supports glob-style patterns: "issue.*", "agent.status_changed", etc.
async fn find_matching_webhooks(
    pool: &SqlitePool,
    company_id: &str,
    event_type: &str,
) -> Result<Vec<Webhook>, sqlx::Error> {
    let webhooks: Vec<Webhook> = sqlx::query_as(
        "SELECT * FROM webhooks WHERE company_id = ? AND active = 1"
    )
        .bind(company_id)
        .fetch_all(pool)
        .await?;

    Ok(webhooks.into_iter().filter(|w| matches_pattern(&w.event_type, event_type)).collect())
}

/// Simple glob pattern matching: "issue.*" matches "issue.created", "issue.status_changed", etc.
/// Exact match also works: "issue.created" only matches "issue.created".
fn matches_pattern(pattern: &str, event_type: &str) -> bool {
    if pattern == event_type {
        return true;
    }
    if pattern.ends_with(".*") {
        let prefix = &pattern[..pattern.len() - 2];
        return event_type.starts_with(prefix) && event_type[prefix.len()..].starts_with('.');
    }
    if pattern.ends_with(".**") {
        let prefix = &pattern[..pattern.len() - 3];
        return event_type.starts_with(prefix);
    }
    false
}

async fn create_delivery(pool: &SqlitePool, webhook: &Webhook, event_id: &str, payload: &str) {
    let id = Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();

    // Build the delivery payload with event metadata
    let delivery_payload = serde_json::json!({
        "event_id": event_id,
        "event_type": serde_json::from_str::<serde_json::Value>(payload)
            .ok()
            .and_then(|v| v.get("event_type").cloned())
            .unwrap_or(serde_json::Value::Null),
        "webhook_id": webhook.id,
        "data": serde_json::from_str::<serde_json::Value>(payload).unwrap_or(serde_json::Value::Null),
        "timestamp": now,
    });
    let payload_str = delivery_payload.to_string();

    if let Err(e) = sqlx::query(
        "INSERT INTO webhook_deliveries (id, webhook_id, event_id, payload, status, attempts, max_attempts, created_at)
         VALUES (?, ?, ?, ?, 'pending', 0, 5, ?)"
    )
        .bind(&id)
        .bind(&webhook.id)
        .bind(event_id)
        .bind(&payload_str)
        .bind(&now)
        .execute(pool)
        .await
    {
        tracing::error!(webhook_id = %webhook.id, error = %e, "Failed to create delivery");
    }
}

/// Run the webhook delivery loop. Called from main.rs as a background task.
/// Picks up pending deliveries and POSTs them with retry logic.
pub async fn run_delivery_worker(pool: SqlitePool, interval_secs: u64) {
    tracing::info!(interval_secs, "Webhook delivery worker started");

    // Add reqwest as a dependency in Cargo.toml
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .unwrap_or_else(|_| reqwest::Client::new());

    loop {
        tokio::time::sleep(std::time::Duration::from_secs(interval_secs)).await;

        match deliver_pending(&pool, &client).await {
            Ok(count) => {
                if count > 0 {
                    tracing::debug!(delivered = count, "Webhook deliveries processed");
                }
            }
            Err(e) => {
                tracing::error!(error = %e, "Webhook delivery loop error");
            }
        }
    }
}

async fn deliver_pending(pool: &SqlitePool, client: &reqwest::Client) -> Result<usize, sqlx::Error> {
    // Find deliveries that are pending or ready for retry
    let deliveries: Vec<WebhookDelivery> = sqlx::query_as(
        "SELECT * FROM webhook_deliveries
         WHERE status IN ('pending', 'retrying')
         AND attempts < max_attempts
         AND (next_retry_at IS NULL OR next_retry_at <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
         ORDER BY created_at ASC
         LIMIT 50"
    )
        .fetch_all(pool)
        .await?;

    let count = deliveries.len();
    let mut succeeded = 0usize;
    let mut failed = 0usize;

    for delivery in deliveries {
        // Fetch the webhook for URL and secret
        let webhook: Option<Webhook> = sqlx::query_as(
            "SELECT * FROM webhooks WHERE id = ?"
        )
            .bind(&delivery.webhook_id)
            .fetch_optional(pool)
            .await?;

        let webhook = match webhook {
            Some(w) => w,
            None => {
                // Webhook was deleted, mark delivery as failed
                sqlx::query("UPDATE webhook_deliveries SET status = 'failed' WHERE id = ?")
                    .bind(&delivery.id)
                    .execute(pool)
                    .await?;
                continue;
            }
        };

        if !webhook.active {
            continue;
        }

        let now = chrono::Utc::now().to_rfc3339();
        let new_attempts = delivery.attempts + 1;

        // Sign the payload with HMAC-SHA256
        let signature = hmac_sha256(&webhook.secret, &delivery.payload);

        // Build the request
        let mut builder = client
            .post(&webhook.target_url)
            .header("Content-Type", "application/json")
            .header("X-GeoForge-Signature", format!("sha256={}", signature))
            .header("X-GeoForge-Event", get_event_type_from_payload(&delivery.payload))
            .header("X-GeoForge-Delivery", &delivery.id);

        // Add custom headers
        if let Ok(extra) = serde_json::from_str::<serde_json::Value>(&webhook.headers) {
            if let Some(obj) = extra.as_object() {
                for (k, v) in obj {
                    if let Some(s) = v.as_str() {
                        builder = builder.header(k, s);
                    }
                }
            }
        }

        match builder.body(delivery.payload.clone()).send().await {
            Ok(resp) => {
                let status_code = resp.status().as_u16() as i64;
                let is_success = resp.status().is_success();
                let body = resp.text().await.unwrap_or_default();

                if is_success {
                    sqlx::query(
                        "UPDATE webhook_deliveries SET status = 'delivered', response_code = ?,
                         response_body = ?, attempts = ?, last_attempt_at = ? WHERE id = ?"
                    )
                        .bind(status_code)
                        .bind(&body)
                        .bind(new_attempts)
                        .bind(&now)
                        .bind(&delivery.id)
                        .execute(pool)
                        .await?;
                    succeeded += 1;
                } else {
                    // Non-2xx: schedule retry
                    let next_retry = calculate_next_retry(new_attempts);
                    sqlx::query(
                        "UPDATE webhook_deliveries SET status = 'retrying', response_code = ?,
                         response_body = ?, attempts = ?, last_attempt_at = ?, next_retry_at = ? WHERE id = ?"
                    )
                        .bind(status_code)
                        .bind(&body)
                        .bind(new_attempts)
                        .bind(&now)
                        .bind(&next_retry)
                        .bind(&delivery.id)
                        .execute(pool)
                        .await?;
                    failed += 1;
                }
            }
            Err(e) => {
                // Network error: schedule retry
                let next_retry = calculate_next_retry(new_attempts);
                sqlx::query(
                    "UPDATE webhook_deliveries SET status = 'retrying', attempts = ?,
                     last_attempt_at = ?, next_retry_at = ?, response_body = ? WHERE id = ?"
                )
                    .bind(new_attempts)
                    .bind(&now)
                    .bind(&next_retry)
                    .bind(format!("Network error: {}", e))
                    .bind(&delivery.id)
                    .execute(pool)
                    .await?;
                failed += 1;
            }
        }
    }

    tracing::debug!(total = count, succeeded, failed, "Delivery batch complete");
    Ok(count)
}

fn calculate_next_retry(attempts: i64) -> String {
    // Exponential backoff: 10s, 30s, 90s, 270s, 810s
    let delay_secs = 10 * 3i64.pow((attempts - 1) as u32);
    let next = chrono::Utc::now() + chrono::Duration::seconds(delay_secs);
    next.to_rfc3339()
}

/// HMAC-SHA256 signing for webhook payloads.
fn hmac_sha256(secret: &str, payload: &str) -> String {
    use std::fmt::Write;
    use hmac::{Hmac, Mac};
    use sha2::Sha256;

    type HmacSha256 = Hmac<Sha256>;

    let mut mac = HmacSha256::new_from_slice(secret.as_bytes())
        .expect("HMAC key creation should not fail");
    mac.update(payload.as_bytes());
    let result = mac.finalize();
    let bytes = result.into_bytes();
    bytes.iter().fold(String::new(), |mut s, b| {
        write!(s, "{:02x}", b).unwrap();
        s
    })
}

fn get_event_type_from_payload(payload: &str) -> String {
    serde_json::from_str::<serde_json::Value>(payload)
        .ok()
        .and_then(|v| v.get("event_type").and_then(|t| t.as_str()).map(|s| s.to_string()))
        .unwrap_or_else(|| "unknown".to_string())
}
