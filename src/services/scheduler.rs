use crate::SharedState;
use crate::services::executor;
use crate::services::timestamps::parse_timestamp;
use cron::Schedule;
use std::time::Duration;

/// Run the scheduler loop.
/// Scans active routines, evaluates their cron expressions, and triggers
/// agent invocations when it's time.
pub async fn run_scheduler(state: SharedState, poll_interval_secs: u64) {
    tracing::info!(
        "Scheduler started (polling every {}s)",
        poll_interval_secs,
    );

    let mut interval = tokio::time::interval(
        Duration::from_secs(poll_interval_secs)
    );

    loop {
        interval.tick().await;

        if let Err(e) = poll_routines(&state).await {
            tracing::error!("Scheduler error: {}", e);
        }
    }
}

async fn poll_routines(state: &SharedState) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let routines = sqlx::query_as::<_, crate::db::models::Routine>(
        "SELECT * FROM routines WHERE status = 'active'"
    )
        .fetch_all(&state.pool)
        .await?;

    let now = chrono::Utc::now();

    for routine in &routines {
        if let Err(e) = process_routine(state, routine, &now).await {
            tracing::error!(
                "Error processing routine {} ({}): {}",
                routine.id,
                routine.title,
                e
            );
        }
    }

    Ok(())
}

async fn process_routine(
    state: &SharedState,
    routine: &crate::db::models::Routine,
    now: &chrono::DateTime<chrono::Utc>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Check if we're in a retry backoff window
    if let Some(ref retry_at) = routine.next_retry_at {
        if let Some(retry_time) = parse_timestamp(retry_at) {
            if *now < retry_time {
                tracing::debug!(
                    "Routine {} in retry backoff until {}",
                    routine.id,
                    retry_at,
                );
                return Ok(());
            }
        }
    }

    let cron_expr = match &routine.cron_expression {
        Some(expr) => expr.clone(),
        None => return Ok(()), // No cron = manual trigger only
    };

    // Parse the cron expression
    let schedule = match cron_expr.parse::<Schedule>() {
        Ok(s) => s,
        Err(e) => {
            tracing::warn!("Invalid cron expression for routine {}: {}", routine.id, e);
            return Ok(());
        }
    };

    // Check if we should trigger based on last_triggered_at
    let last_triggered = routine.last_triggered_at
        .as_ref()
        .and_then(|s| parse_timestamp(s));

    // Find the most recent fire time before now
    // For routines in retry mode (consecutive_failures > 0), also allow firing via retry schedule
    let should_trigger = if routine.consecutive_failures > 0 {
        // In retry mode: fire if retry time has passed (already checked above) or cron fires
        should_fire(&schedule, last_triggered.as_ref(), now)
    } else {
        should_fire(&schedule, last_triggered.as_ref(), now)
    };

    if !should_trigger {
        return Ok(());
    }

    // Check concurrency policy
    let should_skip = match routine.concurrency.as_str() {
        "skip_if_active" => {
            // Check if agent is already running
            let agent = sqlx::query_as::<_, crate::db::models::Agent>(
                "SELECT * FROM agents WHERE id = ?"
            )
                .bind(&routine.assignee_agent_id)
                .fetch_optional(&state.pool)
                .await?;

            agent.map(|a| a.status == "running").unwrap_or(false)
        }
        "queue" => false,
        _ => false,
    };

    if should_skip {
        tracing::debug!(
            "Skipping routine {} -- agent {} is active",
            routine.title,
            routine.assignee_agent_id,
        );
        return Ok(());
    }

    // Find the next available todo issue for this agent (if project-scoped)
    let issue_id = find_issue_for_routine(state, routine).await?;

    tracing::info!(
        "Triggering routine '{}' for agent {}{}",
        routine.title,
        routine.assignee_agent_id,
        issue_id.as_ref().map(|id| format!(" (issue {})", id)).unwrap_or_default(),
    );

    // Update last_triggered_at BEFORE spawning, so we don't re-trigger
    sqlx::query(
        "UPDATE routines SET last_triggered_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(&routine.id)
        .execute(&state.pool)
        .await?;

    // Spawn the invocation so it doesn't block other routine polls (P0-4 fix)
    let state_clone = state.clone();
    let agent_id = routine.assignee_agent_id.clone();
    let routine_title = routine.title.clone();
    let routine_id = routine.id.clone();
    let max_retries = routine.max_retries;
    let retry_interval_secs = routine.retry_interval_secs;
    let consecutive_failures = routine.consecutive_failures;
    tokio::spawn(async move {
        let result = executor::invoke_agent(
            &state_clone,
            &agent_id,
            issue_id.as_deref(),
            "routine",
            Some(&routine_id),
        )
            .await;

        if result.success {
            // Reset consecutive failures on success
            let _ = sqlx::query(
                "UPDATE routines SET consecutive_failures = 0, next_retry_at = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(&routine_id)
                .execute(&state_clone.pool)
                .await;

            tracing::info!(
                "Routine '{}' completed successfully in {}ms",
                routine_title,
                result.duration_ms,
            );
        } else {
            // Increment consecutive failures
            let new_failures = consecutive_failures + 1;
            let _ = sqlx::query(
                "UPDATE routines SET consecutive_failures = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(new_failures)
                .bind(&routine_id)
                .execute(&state_clone.pool)
                .await;

            tracing::warn!(
                "Routine '{}' failed ({}/{}): {}",
                routine_title,
                new_failures,
                max_retries,
                result.output.chars().take(200).collect::<String>(),
            );

            // Check if we've exceeded max retries -> auto-pause agent
            if new_failures >= max_retries {
                tracing::error!(
                    "Routine '{}' exceeded max retries ({}), auto-pausing agent {}",
                    routine_title,
                    max_retries,
                    agent_id,
                );

                let _ = sqlx::query(
                    "UPDATE agents SET status = 'paused', error_message = ?, paused_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
                )
                    .bind(format!("Auto-paused: routine '{}' failed {} consecutive times", routine_title, new_failures))
                    .bind(&agent_id)
                    .execute(&state_clone.pool)
                    .await;

                // Log the auto-pause
                let activity_id = uuid::Uuid::new_v4().to_string();
                let company_id = sqlx::query_scalar::<_, String>(
                    "SELECT company_id FROM agents WHERE id = ?"
                )
                    .bind(&agent_id)
                    .fetch_one(&state_clone.pool)
                    .await
                    .unwrap_or_default();

                let _ = sqlx::query(
                    "INSERT INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details)\
                     VALUES (?, ?, 'system', 'scheduler', 'auto_pause', 'agent', ?, ?)"
                )
                    .bind(&activity_id)
                    .bind(&company_id)
                    .bind(&agent_id)
                    .bind(format!("{{\"reason\": \"max_retries_exceeded\", \"routine\": \"{}\", \"failures\": {}}}", routine_title, new_failures))
                    .execute(&state_clone.pool)
                    .await;

                // Deactivate the routine too
                let _ = sqlx::query(
                    "UPDATE routines SET status = 'inactive', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
                )
                    .bind(&routine_id)
                    .execute(&state_clone.pool)
                    .await;
            } else {
                // Schedule retry with exponential backoff
                let backoff_secs = retry_interval_secs * 2i64.pow(new_failures as u32 - 1);
                let retry_at = chrono::Utc::now() + chrono::Duration::seconds(backoff_secs);
                let retry_str = retry_at.to_rfc3339();
                let _ = sqlx::query(
                    "UPDATE routines SET next_retry_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
                )
                    .bind(&retry_str)
                    .bind(&routine_id)
                    .execute(&state_clone.pool)
                    .await;

                tracing::info!(
                    "Routine '{}' retry #{}/{} scheduled in {}s (at {})",
                    routine_title,
                    new_failures,
                    max_retries,
                    backoff_secs,
                    retry_str,
                );
            }
        }
    });

    Ok(())
}

/// Determine if a cron schedule should fire given the last trigger time and current time.
///
/// P0-5 fix: When `last_triggered` is None (never triggered), we don't fire immediately.
/// Instead, we check if there was a missed fire time between (now - period) and now.
/// For first startup, we skip so the routine waits for its next natural schedule.
fn should_fire(
    schedule: &Schedule,
    last_triggered: Option<&chrono::DateTime<chrono::Utc>>,
    now: &chrono::DateTime<chrono::Utc>,
) -> bool {
    match last_triggered {
        None => {
            // Never triggered -- do NOT fire immediately on first startup.
            // The routine will fire at its next scheduled time.
            false
        }
        Some(last) => {
            // Find the next fire time after last_triggered
            let next_after_last = schedule.after(last).next();
            match next_after_last {
                // Fire if the scheduled time after last is before or equal to now
                Some(fire_time) => fire_time <= *now,
                None => false,
            }
        }
    }
}

/// Find the best issue to work on for a routine.
/// If the routine is project-scoped, find a todo issue in that project.
/// Otherwise, find any todo issue assigned to the agent.
async fn find_issue_for_routine(
    state: &SharedState,
    routine: &crate::db::models::Routine,
) -> Result<Option<String>, sqlx::Error> {
    let issue = if let Some(ref project_id) = routine.project_id {
        sqlx::query_as::<_, crate::db::models::Issue>(
            "SELECT * FROM issues WHERE company_id = ? AND project_id = ? AND status = 'todo' \
             ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, \
             created_at LIMIT 1"
        )
            .bind(&routine.company_id)
            .bind(project_id)
            .fetch_optional(&state.pool)
            .await?
    } else {
        sqlx::query_as::<_, crate::db::models::Issue>(
            "SELECT * FROM issues WHERE company_id = ? AND (assignee_agent_id = ? OR assignee_agent_id IS NULL) AND status = 'todo' \
             ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, \
             created_at LIMIT 1"
        )
            .bind(&routine.company_id)
            .bind(&routine.assignee_agent_id)
            .fetch_optional(&state.pool)
            .await?
    };

    Ok(issue.map(|i| i.id))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_fire_never_triggered_returns_false() {
        let schedule = "0 */5 * * * *".parse::<Schedule>().unwrap();
        let now = chrono::Utc::now();
        // P0-5 fix: should NOT fire when never triggered
        assert!(!should_fire(&schedule, None, &now));
    }

    #[test]
    fn test_should_fire_after_last_triggered() {
        let schedule = "0 */5 * * * *".parse::<Schedule>().unwrap();
        let now = chrono::Utc::now();
        let last = now - chrono::Duration::minutes(10);
        // Should fire since 10 minutes have passed
        assert!(should_fire(&schedule, Some(&last), &now));
    }

    #[test]
    fn test_should_not_fire_when_too_recent() {
        let schedule = "0 0 * * * *".parse::<Schedule>().unwrap(); // hourly
        let now = chrono::Utc::now();
        let last = now - chrono::Duration::seconds(30);
        // Should NOT fire since we just triggered 30 seconds ago
        assert!(!should_fire(&schedule, Some(&last), &now));
    }
}
