use axum::{extract::{Path, State}, response::Json};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::query_as;
use uuid::Uuid;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::AlertRule;

#[derive(Debug, Deserialize)]
pub struct CreateAlertRuleRequest {
    pub name: String,
    pub rule_type: String,       // 'agent_dead', 'issue_blocked', 'no_activity'
    pub threshold_mins: i64,
    pub enabled: Option<bool>,
    pub webhook_url: Option<String>,
}

pub async fn list(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Vec<AlertRule>>> {
    let rules = query_as::<_, AlertRule>(
        "SELECT * FROM alert_rules WHERE company_id = ? ORDER BY created_at"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(rules))
}

pub async fn create(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
    Json(body): Json<CreateAlertRuleRequest>,
) -> AppResult<Json<AlertRule>> {
    // Validate rule_type
    crate::validation::validate_enum(&body.rule_type, "rule_type", crate::validation::VALID_ALERT_TYPES)?;
    crate::validation::require_non_empty(&body.name, "name")?;
    crate::validation::validate_length(&body.name, "name", crate::validation::MAX_NAME_LEN)?;
    crate::validation::validate_opt_webhook_url(&body.webhook_url)?;
    if body.threshold_mins < 0 {
        return Err(AppError::Validation("threshold_mins must be >= 0".to_string()));
    }

    let id = Uuid::new_v4().to_string();
    let enabled = body.enabled.unwrap_or(true) as i64;

    sqlx::query(
        "INSERT INTO alert_rules (id, company_id, name, rule_type, threshold_mins, enabled, webhook_url)
         VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
        .bind(&id)
        .bind(&cid)
        .bind(&body.name)
        .bind(&body.rule_type)
        .bind(&body.threshold_mins)
        .bind(&enabled)
        .bind(&body.webhook_url)
        .execute(&state.pool)
        .await?;

    let rule = query_as::<_, AlertRule>("SELECT * FROM alert_rules WHERE id = ?")
        .bind(&id)
        .fetch_one(&state.pool)
        .await?;

    Ok(Json(rule))
}

pub async fn delete(
    State(state): State<SharedState>,
    Path(rid): Path<String>,
) -> AppResult<Json<Value>> {
    let _rule = query_as::<_, AlertRule>("SELECT * FROM alert_rules WHERE id = ?")
        .bind(&rid)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Alert rule {} not found", rid)))?;

    sqlx::query("DELETE FROM alert_rules WHERE id = ?")
        .bind(&rid)
        .execute(&state.pool)
        .await?;

    Ok(Json(json!({"deleted": true, "id": rid})))
}

/// Evaluate all enabled alert rules for a company.
/// Returns a list of fired alerts.
pub async fn evaluate(
    State(state): State<SharedState>,
    Path(cid): Path<String>,
) -> AppResult<Json<Value>> {
    let rules = query_as::<_, AlertRule>(
        "SELECT * FROM alert_rules WHERE company_id = ? AND enabled = 1"
    )
        .bind(&cid)
        .fetch_all(&state.pool)
        .await?;

    let mut fired: Vec<Value> = Vec::new();

    for rule in &rules {
        let violations = match rule.rule_type.as_str() {
            "agent_dead" => eval_agent_dead(&state, &cid, rule.threshold_mins).await,
            "issue_blocked" => eval_issue_blocked(&state, &cid, rule.threshold_mins).await,
            "no_activity" => eval_no_activity(&state, &cid, rule.threshold_mins).await,
            _ => Vec::new(),
        };

        for v in &violations {
            // Log to activity_log
            let detail = json!({
                "alert_rule_id": rule.id,
                "rule_name": rule.name,
                "rule_type": rule.rule_type,
                "violation": v,
            });
            log_alert(&state, &cid, "alert.fired", &rule.id, &detail.to_string()).await;

            // Fire webhook if configured
            if let Some(ref url) = rule.webhook_url {
                if let Err(e) = fire_webhook(url, &detail).await {
                    tracing::warn!("Webhook delivery failed for rule {}: {}", rule.id, e);
                }
            }
        }

        if !violations.is_empty() {
            // Update last_fired_at
            let _ = sqlx::query(
                "UPDATE alert_rules SET last_fired_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(&rule.id)
                .execute(&state.pool)
                .await;

            fired.push(json!({
                "ruleId": rule.id,
                "ruleName": rule.name,
                "ruleType": rule.rule_type,
                "violations": violations,
            }));
        }
    }

    Ok(Json(json!({
        "companyId": cid,
        "evaluatedRules": rules.len(),
        "firedAlerts": fired.len(),
        "alerts": fired,
    })))
}

// -- Evaluation helpers --

async fn eval_agent_dead(state: &SharedState, cid: &str, threshold_mins: i64) -> Vec<Value> {
    // Find agents with last_heartbeat older than threshold (or never heartbeated)
    let agents: Vec<(String, String, Option<String>)> = sqlx::query_as(
        "SELECT id, name, last_heartbeat FROM agents \
         WHERE company_id = ? AND status IN ('idle', 'running') \
         AND (last_heartbeat IS NULL OR last_heartbeat < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ? || ' minutes'))"
    )
        .bind(cid)
        .bind(format!("-{}", threshold_mins))
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    agents.into_iter().map(|(id, name, hb)| {
        json!({
            "agentId": id,
            "agentName": name,
            "lastHeartbeat": hb,
            "deadFor": format!("{}m", threshold_mins),
        })
    }).collect()
}

async fn eval_issue_blocked(state: &SharedState, cid: &str, threshold_mins: i64) -> Vec<Value> {
    // Find issues in backlog with blocked_by that have been stuck longer than threshold
    let issues: Vec<(String, String, Option<String>)> = sqlx::query_as(
        "SELECT identifier, title, updated_at FROM issues \
         WHERE company_id = ? AND status = 'backlog' AND blocked_by != '[]' \
         AND updated_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ? || ' minutes')"
    )
        .bind(cid)
        .bind(format!("-{}", threshold_mins))
        .fetch_all(&state.pool)
        .await
        .unwrap_or_default();

    issues.into_iter().map(|(ident, title, updated)| {
        json!({
            "identifier": ident,
            "title": title,
            "updatedAt": updated,
            "blockedFor": format!("{}m", threshold_mins),
        })
    }).collect()
}

async fn eval_no_activity(state: &SharedState, cid: &str, threshold_mins: i64) -> Vec<Value> {
    // Check if the company has had any activity_log entries in the last threshold minutes
    let count: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM activity_log \
         WHERE company_id = ? AND created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ? || ' minutes')"
    )
        .bind(cid)
        .bind(format!("-{}", threshold_mins))
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

    if count.0 == 0 {
        vec![json!({
            "type": "no_activity",
            "threshold": format!("{}m", threshold_mins),
            "message": format!("No activity in the last {} minutes", threshold_mins),
        })]
    } else {
        Vec::new()
    }
}

async fn log_alert(state: &SharedState, company_id: &str, action: &str, rule_id: &str, details: &str) {
    let id = Uuid::new_v4().to_string();
    let _ = sqlx::query(
        "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)
         VALUES (?, ?, 'system', ?, ?, 'alert_rule', ?, ?)"
    )
        .bind(&id)
        .bind(company_id)
        .bind(rule_id)
        .bind(action)
        .bind(rule_id)
        .bind(details)
        .execute(&state.pool)
        .await;
}

async fn fire_webhook(url: &str, payload: &Value) -> Result<(), String> {
    let client = reqwest::Client::new();
    client.post(url)
        .json(payload)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
        .map_err(|e| format!("Webhook request failed: {}", e))?;
    Ok(())
}
