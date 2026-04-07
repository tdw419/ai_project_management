use crate::SharedState;
use crate::config::HealthConfig;
use crate::services::timestamps::parse_timestamp;

/// Run the health monitor as a background task.
/// Checks all active agents periodically and updates their health_status.
pub async fn run_health_monitor(state: SharedState, cfg: &HealthConfig) {
    let check_interval_secs = cfg.check_interval_secs;
    let stale = cfg.stale_threshold_secs;
    let dead = cfg.dead_threshold_secs;

    tracing::info!(
        "Health monitor started (checking every {}s, stale={}s, dead={}s)",
        check_interval_secs,
        stale,
        dead,
    );

    let mut interval = tokio::time::interval(
        std::time::Duration::from_secs(check_interval_secs)
    );

    loop {
        interval.tick().await;

        if let Err(e) = check_agents(&state, stale, dead).await {
            tracing::error!("Health monitor error: {}", e);
        }
    }
}

async fn check_agents(state: &SharedState, stale_secs: u64, dead_secs: u64) -> Result<(), sqlx::Error> {
    let agents = sqlx::query_as::<_, crate::db::models::Agent>(
        "SELECT * FROM agents WHERE status NOT IN ('paused')"
    )
        .fetch_all(&state.pool)
        .await?;

    let now = chrono::Utc::now();
    let mut stale_count = 0u32;
    let mut dead_count = 0u32;
    let mut healthy_count = 0u32;

    for agent in &agents {
        let health = compute_health(agent, &now, stale_secs, dead_secs);
        if health != agent.health_status {
            let _ = sqlx::query(
                "UPDATE agents SET health_status = ?, health_check_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(&health)
                .bind(&agent.id)
                .execute(&state.pool)
                .await;

            match health.as_str() {
                "stale" => stale_count += 1,
                "dead" => {
                    dead_count += 1;
                    // Mark dead agents as error status so they stop getting dispatched
                    let _ = sqlx::query(
                        "UPDATE agents SET status = 'error', error_message = 'Agent heartbeat lost (marked dead by health monitor)', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ? AND status = 'running'"
                    )
                        .bind(&agent.id)
                        .execute(&state.pool)
                        .await;
                }
                _ => healthy_count += 1,
            }
        } else {
            healthy_count += 1;
        }
    }

    if stale_count > 0 || dead_count > 0 {
        tracing::warn!(
            "Health check: {} healthy, {} stale, {} dead",
            healthy_count,
            stale_count,
            dead_count,
        );
    } else {
        tracing::debug!("Health check: all {} agents healthy", healthy_count);
    }

    Ok(())
}

fn compute_health(agent: &crate::db::models::Agent, now: &chrono::DateTime<chrono::Utc>, stale_secs: u64, dead_secs: u64) -> String {
    let last_hb = agent.last_heartbeat
        .as_ref()
        .and_then(|s| parse_timestamp(s));

    match last_hb {
        None => {
            // Never heartbeaten -- if recently created, give grace
            let created = parse_timestamp(&agent.created_at);
            match created {
                Some(c) => {
                    let secs = (*now - &c).num_seconds().unsigned_abs();
                    if secs < stale_secs {
                        "unknown".to_string()
                    } else {
                        "dead".to_string()
                    }
                }
                None => "unknown".to_string(),
            }
        }
        Some(hb) => {
            let secs = (*now - &hb).num_seconds().unsigned_abs();
            if secs < stale_secs {
                "healthy".to_string()
            } else if secs < dead_secs {
                "stale".to_string()
            } else {
                "dead".to_string()
            }
        }
    }
}
