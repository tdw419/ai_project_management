use std::process::Stdio;
use tokio::process::Command;
use uuid::Uuid;
use crate::SharedState;

/// Result of an agent invocation attempt.
#[derive(Debug)]
pub struct InvokeResult {
    pub success: bool,
    pub output: String,
    pub duration_ms: u64,
    pub invocation_id: Option<String>,
    /// True if work was dispatched to a persistent worker (geo_harness)
    /// rather than executed inline via child process.
    pub dispatched: bool,
}

/// Invoke an agent via the appropriate adapter and record the invocation.
///
/// Two dispatch modes based on `adapter_type`:
///
/// **hermes_local** -- Spawns a child process (default: `hermes` CLI).
/// The agent's adapter_config JSON can contain:
///   - `command`: override the command (default: "hermes")
///   - `args`: additional CLI arguments
///   - `env`: environment variables to set
///   - `working_dir`: working directory
///
/// **geo_harness** -- Assigns the issue and returns immediately.
/// The agent is expected to be a persistent worker (geo-harness service)
/// that polls for assigned issues and runs its own LLM loop. No child
/// process is spawned. The invocation record is marked as "dispatched".
pub async fn invoke_agent(
    state: &SharedState,
    agent_id: &str,
    issue_id: Option<&str>,
    triggered_by: &str,
    routine_id: Option<&str>,
) -> InvokeResult {
    let start = std::time::Instant::now();

    // Fetch agent details
    let agent = match sqlx::query_as::<_, crate::db::models::Agent>(
        "SELECT * FROM agents WHERE id = ?"
    )
        .bind(agent_id)
        .fetch_optional(&state.pool)
        .await
    {
        Ok(Some(a)) => a,
        Ok(None) => {
            return InvokeResult {
                success: false,
                output: format!("Agent {} not found", agent_id),
                duration_ms: start.elapsed().as_millis() as u64,
                invocation_id: None,
                dispatched: false,
            };
        }
        Err(e) => {
            return InvokeResult {
                success: false,
                output: format!("DB error fetching agent: {}", e),
                duration_ms: start.elapsed().as_millis() as u64,
                invocation_id: None,
                dispatched: false,
            };
        }
    };

    let company_id = agent.company_id.clone();

    // Skip paused agents
    if agent.status == "paused" {
        return InvokeResult {
            success: false,
            output: format!("Agent {} is paused, skipping", agent.name),
            duration_ms: start.elapsed().as_millis() as u64,
            invocation_id: None,
            dispatched: false,
        };
    }

    // Determine adapter type (default: geo_harness for new-style workers)
    let adapter_type = if agent.adapter_type.is_empty() {
        "geo_harness"
    } else {
        &agent.adapter_type
    };

    // Create invocation record
    let invocation_id = Uuid::new_v4().to_string();
    let _ = sqlx::query(
        "INSERT INTO invocations (id, agent_id, company_id, issue_id, routine_id, triggered_by, started_at)
         VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
        .bind(&invocation_id)
        .bind(agent_id)
        .bind(&company_id)
        .bind(issue_id)
        .bind(routine_id)
        .bind(triggered_by)
        .execute(&state.pool)
        .await;

    // Mark agent as running
    let _ = sqlx::query(
        "UPDATE agents SET status = 'running', last_heartbeat = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
    )
        .bind(agent_id)
        .execute(&state.pool)
        .await;

    // Assign issue to agent if one was provided
    if let Some(iid) = issue_id {
        let _ = sqlx::query(
            "UPDATE agents SET current_issue_id = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
        )
            .bind(iid)
            .bind(agent_id)
            .execute(&state.pool)
            .await;
    }

    // ================================================================
    // geo_harness dispatch: assign + return. Worker polls for work.
    // ================================================================
    if adapter_type == "geo_harness" {
        // Create routine_runs record if this is a routine invocation
        if let Some(rid) = routine_id {
            let run_id = Uuid::new_v4().to_string();
            let _ = sqlx::query(
                "INSERT INTO routine_runs (id, routine_id, agent_id, company_id, issue_id, triggered_by, status, started_at)
                 VALUES (?, ?, ?, ?, ?, ?, 'dispatched', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
            )
                .bind(&run_id)
                .bind(rid)
                .bind(agent_id)
                .bind(&company_id)
                .bind(issue_id)
                .bind(triggered_by)
                .execute(&state.pool)
                .await;
        }

        tracing::info!(
            "Dispatched issue {} to agent {} ({}) via geo_harness [triggered_by={}]",
            issue_id.unwrap_or("none"),
            agent.name,
            agent_id,
            triggered_by,
        );

        return InvokeResult {
            success: true,
            output: format!("Dispatched to geo_harness worker: {}", agent.name),
            duration_ms: start.elapsed().as_millis() as u64,
            invocation_id: Some(invocation_id),
            dispatched: true,
        };
    }

    // ================================================================
    // hermes_local dispatch: spawn child process and wait for exit.
    // ================================================================

    // Create routine_runs record if this is a routine invocation
    let routine_run_id = if let Some(rid) = routine_id {
        let run_id = Uuid::new_v4().to_string();
        let _ = sqlx::query(
            "INSERT INTO routine_runs (id, routine_id, agent_id, company_id, issue_id, triggered_by, status, started_at)
             VALUES (?, ?, ?, ?, ?, ?, 'running', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
        )
            .bind(&run_id)
            .bind(rid)
            .bind(agent_id)
            .bind(&company_id)
            .bind(issue_id)
            .bind(triggered_by)
            .execute(&state.pool)
            .await;
        Some(run_id)
    } else {
        None
    };

    // Parse adapter config
    let config: serde_json::Value =
        serde_json::from_str(&agent.adapter_config).unwrap_or_default();

    let command = config.get("command")
        .and_then(|v| v.as_str())
        .unwrap_or("hermes");

    let mut args: Vec<String> = config.get("args")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    // If we have an issue, pass it as a prompt to the agent
    if let Some(iid) = issue_id {
        // Fetch issue details for context
        let issue = sqlx::query_as::<_, crate::db::models::Issue>(
            "SELECT * FROM issues WHERE id = ?"
        )
            .bind(iid)
            .fetch_optional(&state.pool)
            .await
            .ok()
            .flatten();

        if let Some(issue) = issue {
            args.push("--prompt".to_string());
            args.push(format!(
                "Work on {}: {}",
                issue.identifier.as_deref().unwrap_or(iid),
                issue.title
            ));
        }
    }

    tracing::info!(
        "Invoking agent {} ({}) via: {} {} [triggered_by={}]",
        agent.name,
        agent_id,
        command,
        args.join(" "),
        triggered_by,
    );

    // Build the command
    let mut cmd = Command::new(command);
    cmd.args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // Set environment variables from config
    if let Some(env) = config.get("env").and_then(|v| v.as_object()) {
        for (key, value) in env {
            if let Some(val_str) = value.as_str() {
                cmd.env(key, val_str);
            }
        }
    }

    // Set working directory
    if let Some(dir) = config.get("working_dir").and_then(|v| v.as_str()) {
        cmd.current_dir(dir);
    }

    // Execute with timeout (default 10 minutes)
    let timeout_secs = config.get("timeout_secs")
        .and_then(|v| v.as_u64())
        .unwrap_or(600);

    let result = tokio::time::timeout(
        std::time::Duration::from_secs(timeout_secs),
        cmd.output(),
    )
        .await;

    let duration_ms = start.elapsed().as_millis() as u64;

    match result {
        Ok(Ok(output)) => {
            let stdout = String::from_utf8_lossy(&output.stdout).to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).to_string();
            let combined = if stderr.is_empty() {
                stdout
            } else {
                format!("{}\n{}", stdout, stderr)
            };

            let success = output.status.success();
            let exit_code = output.status.code();

            // Update agent status based on result
            let new_status = if success { "idle" } else { "error" };
            let _ = sqlx::query(
                "UPDATE agents SET status = ?, last_heartbeat = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(new_status)
                .bind(agent_id)
                .execute(&state.pool)
                .await;

            if !success {
                let err_msg = &combined[..combined.len().min(500)];
                let _ = sqlx::query(
                    "UPDATE agents SET error_message = ? WHERE id = ?"
                )
                    .bind(err_msg)
                    .bind(agent_id)
                    .execute(&state.pool)
                    .await;
            }

            // Update invocation record
            let output_truncated = &combined[..combined.len().min(2000)];
            let _ = sqlx::query(
                "UPDATE invocations SET completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                 exit_code = ?, success = ?, output_truncated = ?, duration_ms = ? WHERE id = ?"
            )
                .bind(exit_code)
                .bind(success)
                .bind(output_truncated)
                .bind(duration_ms as i64)
                .bind(&invocation_id)
                .execute(&state.pool)
                .await;

            // Update routine_runs record
            if let Some(ref run_id) = routine_run_id {
                let run_status = if success { "completed" } else { "failed" };
                let output_snippet = &combined[..combined.len().min(1000)];
                let _ = sqlx::query(
                    "UPDATE routine_runs SET status = ?, output = ?, completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), duration_ms = ? WHERE id = ?"
                )
                    .bind(run_status)
                    .bind(output_snippet)
                    .bind(duration_ms as i64)
                    .bind(run_id)
                    .execute(&state.pool)
                    .await;
            }

            tracing::info!(
                "Agent {} ({}) completed in {}ms, success={}",
                agent.name,
                agent_id,
                duration_ms,
                success
            );

            InvokeResult {
                success,
                output: combined,
                duration_ms,
                invocation_id: Some(invocation_id),
                dispatched: false,
            }
        }
        Ok(Err(e)) => {
            // Command failed to start
            let _ = sqlx::query(
                "UPDATE agents SET status = 'error', error_message = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(e.to_string())
                .bind(agent_id)
                .execute(&state.pool)
                .await;

            let _ = sqlx::query(
                "UPDATE invocations SET completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                 success = 0, output_truncated = ?, duration_ms = ? WHERE id = ?"
            )
                .bind(e.to_string())
                .bind(duration_ms as i64)
                .bind(&invocation_id)
                .execute(&state.pool)
                .await;

            // Update routine_runs record
            if let Some(ref run_id) = routine_run_id {
                let _ = sqlx::query(
                    "UPDATE routine_runs SET status = 'failed', output = ?, completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), duration_ms = ? WHERE id = ?"
                )
                    .bind(e.to_string())
                    .bind(duration_ms as i64)
                    .bind(run_id)
                    .execute(&state.pool)
                    .await;
            }

            InvokeResult {
                success: false,
                output: format!("Failed to execute: {}", e),
                duration_ms,
                invocation_id: Some(invocation_id),
                dispatched: false,
            }
        }
        Err(_) => {
            // Timeout
            let _ = sqlx::query(
                "UPDATE agents SET status = 'error', error_message = 'Execution timed out', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?"
            )
                .bind(agent_id)
                .execute(&state.pool)
                .await;

            let _ = sqlx::query(
                "UPDATE invocations SET completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                 success = 0, output_truncated = 'Execution timed out', duration_ms = ? WHERE id = ?"
            )
                .bind(duration_ms as i64)
                .bind(&invocation_id)
                .execute(&state.pool)
                .await;

            // Update routine_runs record
            if let Some(ref run_id) = routine_run_id {
                let _ = sqlx::query(
                    "UPDATE routine_runs SET status = 'timeout', output = 'Execution timed out', completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), duration_ms = ? WHERE id = ?"
                )
                    .bind(duration_ms as i64)
                    .bind(run_id)
                    .execute(&state.pool)
                    .await;
            }

            InvokeResult {
                success: false,
                output: format!("Execution timed out after {}s", timeout_secs),
                duration_ms,
                invocation_id: Some(invocation_id),
                dispatched: false,
            }
        }
    }
}
