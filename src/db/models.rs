use serde::{Deserialize, Serialize};

// -- Models matching the DB schema --

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Company {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub status: String,
    pub issue_prefix: String,
    pub issue_counter: i64,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Agent {
    pub id: String,
    pub company_id: String,
    pub name: String,
    pub role: String,
    pub status: String,
    pub adapter_type: String,
    pub adapter_config: String, // JSON string
    pub runtime_config: String, // JSON string
    pub reports_to: Option<String>,
    pub permissions: String, // JSON string
    pub last_heartbeat: Option<String>,
    pub paused_at: Option<String>,
    pub error_message: Option<String>,
    pub health_status: String,
    pub health_check_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Issue {
    pub id: String,
    pub company_id: String,
    pub project_id: Option<String>,
    pub parent_id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub status: String,
    pub priority: String,
    pub assignee_agent_id: Option<String>,
    pub identifier: Option<String>,
    pub issue_number: Option<i64>,
    pub origin_kind: String,
    pub origin_id: Option<String>,
    pub blocked_by: Option<String>, // JSON array
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct IssueComment {
    pub id: String,
    pub issue_id: String,
    pub body: String,
    pub author_agent_id: Option<String>,
    pub author_user_id: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Project {
    pub id: String,
    pub company_id: String,
    pub name: String,
    pub description: Option<String>,
    pub status: String,
    pub color: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Goal {
    pub id: String,
    pub company_id: String,
    pub title: String,
    pub description: Option<String>,
    pub level: String,
    pub status: String,
    pub parent_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Label {
    pub id: String,
    pub company_id: String,
    pub name: String,
    pub color: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Routine {
    pub id: String,
    pub company_id: String,
    pub project_id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub assignee_agent_id: String,
    pub cron_expression: Option<String>,
    pub status: String,
    pub concurrency: String,
    pub last_triggered_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct ActivityLog {
    pub id: String,
    pub company_id: String,
    pub actor_type: String,
    pub actor_id: String,
    pub action: String,
    pub entity_type: String,
    pub entity_id: String,
    pub details: Option<String>,
    pub created_at: String,
}

// -- Request/Response DTOs --

#[derive(Debug, Deserialize)]
pub struct CreateAgentRequest {
    pub name: String,
    pub role: Option<String>,
    pub adapter_type: Option<String>,
    pub adapter_config: Option<serde_json::Value>,
    pub runtime_config: Option<serde_json::Value>,
    pub reports_to: Option<String>,
    pub permissions: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateAgentRequest {
    pub name: Option<String>,
    pub role: Option<String>,
    pub status: Option<String>,
    pub adapter_type: Option<String>,
    pub adapter_config: Option<serde_json::Value>,
    pub runtime_config: Option<serde_json::Value>,
    pub permissions: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
pub struct CreateIssueRequest {
    pub title: String,
    pub description: Option<String>,
    pub priority: Option<String>,
    pub project_id: Option<String>,
    pub parent_id: Option<String>,
    pub assignee_agent_id: Option<String>,
    pub origin_kind: Option<String>,
    pub origin_id: Option<String>,
    pub blocked_by: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateIssueRequest {
    pub title: Option<String>,
    pub description: Option<String>,
    pub status: Option<String>,
    pub priority: Option<String>,
    pub assignee_agent_id: Option<String>,
    pub project_id: Option<String>,
    pub blocked_by: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct CheckoutRequest {
    pub agent_id: String,
    pub expected_statuses: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct CreateCommentRequest {
    pub body: String,
}

#[derive(Debug, Deserialize)]
pub struct CreateRoutineRequest {
    pub title: String,
    pub description: Option<String>,
    pub assignee_agent_id: String,
    pub cron_expression: Option<String>,
    pub project_id: Option<String>,
    pub concurrency: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct DispatchRequest {
    pub role: Option<String>,
    pub agent_id: Option<String>,
    pub issue_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct DashboardResponse {
    pub company_id: String,
    pub agents: AgentSummary,
    pub tasks: TaskSummary,
}

#[derive(Debug, Serialize)]
pub struct AgentSummary {
    pub active: i64,
    pub idle: i64,
    pub paused: i64,
    pub error: i64,
}

#[derive(Debug, Serialize)]
pub struct TaskSummary {
    pub backlog: i64,
    pub todo: i64,
    pub in_progress: i64,
    pub in_review: i64,
    pub done: i64,
    pub cancelled: i64,
}
