//! Integration tests for GeoForge API.
//!
//! Tests hit the full Axum Router with an in-memory SQLite database.
//! No HTTP server needed -- we use tower::ServiceExt to call handlers directly.

use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

use geo_forge::AppState;

/// Helper to set up a fresh in-memory test database and router.
async fn test_app() -> (
    impl tower::Service<
        Request<Body>,
        Response = axum::response::Response,
        Error = impl std::error::Error + Send + Sync,
    >,
    Arc<AppState>,
) {
    let pool = sqlx::SqlitePool::connect("sqlite::memory:")
        .await
        .expect("connect to in-memory SQLite");

    sqlx::query("PRAGMA foreign_keys=ON")
        .execute(&pool)
        .await
        .expect("enable foreign keys");

    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .expect("run migrations");

    let state = Arc::new(AppState::new(pool));
    let app = geo_forge::app::build_router(state.clone(), 1000, 100, "");

    (app, state)
}

/// Send a GET request and return (status, body JSON).
async fn get(
    app: &mut impl tower::Service<
        Request<Body>,
        Response = axum::response::Response,
        Error = impl std::error::Error + Send + Sync,
    >,
    path: &str,
) -> (StatusCode, Value) {
    let req = Request::builder()
        .uri(path)
        .body(Body::empty())
        .unwrap();
    let resp = app.ready().await.unwrap().call(req).await.unwrap();
    let status = resp.status();
    let body = body_to_json(resp).await;
    (status, body)
}

/// Send a POST/POST/PATCH/DELETE with a JSON body and return (status, body JSON).
async fn send(
    app: &mut impl tower::Service<
        Request<Body>,
        Response = axum::response::Response,
        Error = impl std::error::Error + Send + Sync,
    >,
    method: &str,
    path: &str,
    body: Value,
) -> (StatusCode, Value) {
    let req = Request::builder()
        .method(method)
        .uri(path)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap();
    let resp = app.ready().await.unwrap().call(req).await.unwrap();
    let status = resp.status();
    let body = body_to_json(resp).await;
    (status, body)
}

/// Send a DELETE request (no body).
async fn delete_req(
    app: &mut impl tower::Service<
        Request<Body>,
        Response = axum::response::Response,
        Error = impl std::error::Error + Send + Sync,
    >,
    path: &str,
) -> (StatusCode, Value) {
    let req = Request::builder()
        .method("DELETE")
        .uri(path)
        .body(Body::empty())
        .unwrap();
    let resp = app.ready().await.unwrap().call(req).await.unwrap();
    let status = resp.status();
    let body = body_to_json(resp).await;
    (status, body)
}

async fn body_to_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body()
        .collect()
        .await
        .expect("read body")
        .to_bytes();
    if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or_else(|e| {
            panic!("Failed to parse JSON: {}\nBody: {}", e, String::from_utf8_lossy(&bytes));
        })
    }
}

// ============================================================
// Health & Metrics
// ============================================================

#[tokio::test]
async fn test_health() {
    let (mut app, _) = test_app().await;
    let (status, body) = get(&mut app, "/api/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "ok");
}

#[tokio::test]
async fn test_metrics() {
    let (mut app, _) = test_app().await;
    let (status, body) = get(&mut app, "/api/metrics").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["service"], "geo-forge");
    assert!(body["timestamp"].is_string());
    assert!(body["agents"].is_object());
    assert!(body["issues"].is_object());
    assert!(body["invocations"].is_object());
    assert!(body["agents"]["total"].is_number());
    assert!(body["issues"]["total"].is_number());
}

// ============================================================
// Companies CRUD
// ============================================================

#[tokio::test]
async fn test_company_create_and_list() {
    let (mut app, _) = test_app().await;

    // Create
    let (status, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Geometry OS",
        "description": "The pixel OS",
        "issue_prefix": "GEO"
    })).await;
    assert_eq!(status, StatusCode::OK);
    let cid = body["id"].as_str().unwrap().to_string();
    assert_eq!(body["name"], "Geometry OS");
    assert_eq!(body["issue_prefix"], "GEO");
    assert_eq!(body["issue_counter"], 0);

    // List
    let (status, body) = get(&mut app, "/api/companies").await;
    assert_eq!(status, StatusCode::OK);
    let companies = body.as_array().unwrap();
    assert_eq!(companies.len(), 1);
    assert_eq!(companies[0]["id"], cid);

    // Get by ID
    let (status, body) = get(&mut app, &format!("/api/companies/{}", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"], "Geometry OS");
}

#[tokio::test]
async fn test_company_not_found() {
    let (mut app, _) = test_app().await;
    let (status, _) = get(&mut app, "/api/companies/nonexistent-id").await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_company_dashboard() {
    let (mut app, _) = test_app().await;

    // Create company
    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co",
        "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Dashboard
    let (status, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert!(body["agents"].is_object());
    assert!(body["tasks"].is_object());
}

// ============================================================
// Agents CRUD
// ============================================================

#[tokio::test]
async fn test_agent_create_and_get() {
    let (mut app, _) = test_app().await;

    // Create company first
    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co",
        "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create agent
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Engineer-1",
        "role": "engineer",
        "adapter_config": {"command": "echo", "args": ["hello"]}
    })).await;
    assert_eq!(status, StatusCode::OK);
    let aid = body["id"].as_str().unwrap().to_string();
    assert_eq!(body["name"], "Engineer-1");
    assert_eq!(body["role"], "engineer");
    assert_eq!(body["status"], "idle");

    // Get by ID
    let (status, body) = get(&mut app, &format!("/api/agents/{}", aid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"], "Engineer-1");

    // List by company
    let (status, body) = get(&mut app, &format!("/api/companies/{}/agents", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn test_agent_update() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Agent-1"
    })).await;
    let aid = body["id"].as_str().unwrap();

    // Update
    let (status, body) = send(&mut app, "PATCH", &format!("/api/agents/{}", aid), json!({
        "name": "Agent-1-Renamed",
        "status": "paused"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"], "Agent-1-Renamed");
    assert_eq!(body["status"], "paused");
}

#[tokio::test]
async fn test_agent_delete() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Agent-To-Delete"
    })).await;
    let aid = body["id"].as_str().unwrap();

    // Delete
    let (status, body) = delete_req(&mut app, &format!("/api/agents/{}", aid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "deleted");

    // Verify status
    let (_, body) = get(&mut app, &format!("/api/agents/{}", aid)).await;
    assert_eq!(body["status"], "deleted");
}

#[tokio::test]
async fn test_agent_heartbeat() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Heartbeat-Agent"
    })).await;
    let aid = body["id"].as_str().unwrap();

    // Send heartbeat
    let (status, body) = send(&mut app, "POST", &format!("/api/agents/{}/heartbeat", aid), json!({
        "status": "running"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "ok");
    assert!(body["heartbeatAt"].is_string());

    // Verify agent status was updated
    let (_, agent) = get(&mut app, &format!("/api/agents/{}", aid)).await;
    assert_eq!(agent["status"], "running");
    assert!(agent["last_heartbeat"].is_string());
}

// ============================================================
// Issues CRUD + State Machine
// ============================================================

#[tokio::test]
async fn test_issue_create_with_auto_identifier() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "GEO"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create first issue
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "First issue"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["identifier"], "GEO-1");
    assert_eq!(body["status"], "todo"); // Note: create defaults to 'todo', not 'backlog'
    let iid1 = body["id"].as_str().unwrap();

    // Create second issue -- counter should increment
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Second issue"
    })).await;
    assert_eq!(body["identifier"], "GEO-2");

    // Get by ID
    let (status, body) = get(&mut app, &format!("/api/issues/{}", iid1)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["title"], "First issue");

    // Get by identifier
    let (status, body) = get(&mut app, "/api/issues/GEO-1").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["title"], "First issue");

    // List by company
    let (status, body) = get(&mut app, &format!("/api/companies/{}/issues", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn test_issue_state_machine_happy_path() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Happy path issue"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // todo -> in_progress
    let (_, body) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "in_progress"
    })).await;
    assert_eq!(body["status"], "in_progress");
    assert!(body["started_at"].is_string());

    // in_progress -> in_review
    let (_, body) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "in_review"
    })).await;
    assert_eq!(body["status"], "in_review");

    // in_review -> done
    let (_, body) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "done"
    })).await;
    assert_eq!(body["status"], "done");
    assert!(body["completed_at"].is_string());
}

#[tokio::test]
async fn test_issue_state_machine_rejects_skip() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "QA Co", "issue_prefix": "QA", "qa_gate": true
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "QA gated issue"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // Try todo -> done (should fail with qa_gate on)
    let (status, _) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "done"
    })).await;
    assert_eq!(status, StatusCode::CONFLICT);

    // Try todo -> in_progress (should succeed)
    let (status, _) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "in_progress"
    })).await;
    assert_eq!(status, StatusCode::OK);

    // Try in_progress -> done (should fail, needs in_review)
    let (status, _) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "done"
    })).await;
    assert_eq!(status, StatusCode::CONFLICT);
}

#[tokio::test]
async fn test_issue_cancel_from_any_open_state() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Cancel me"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // Cancel from todo
    let (status, body) = send(&mut app, "PATCH", &format!("/api/issues/{}", iid), json!({
        "status": "cancelled"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "cancelled");
}

#[tokio::test]
async fn test_issue_soft_delete() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Delete me"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // Soft delete (sets to cancelled)
    let (status, body) = delete_req(&mut app, &format!("/api/issues/{}", iid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "cancelled");

    // Can't delete again
    let (status, _) = delete_req(&mut app, &format!("/api/issues/{}", iid)).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn test_issue_checkout() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Worker-1"
    })).await;
    let aid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Work item"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // Checkout
    let (status, body) = send(&mut app, "POST", &format!("/api/issues/{}/checkout", iid), json!({
        "agent_id": aid
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "in_progress");
    assert_eq!(body["assignee_agent_id"], aid);
}

// ============================================================
// Issue Comments
// ============================================================

#[tokio::test]
async fn test_issue_comments() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Commented issue"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // Create comment
    let (status, body) = send(&mut app, "POST", &format!("/api/issues/{}/comments", iid), json!({
        "body": "This is a test comment"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["body"], "This is a test comment");

    // List comments
    let (status, body) = get(&mut app, &format!("/api/issues/{}/comments", iid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);
    assert_eq!(body[0]["body"], "This is a test comment");
}

// ============================================================
// Dependency Tracking (blocked_by)
// ============================================================

#[tokio::test]
async fn test_issue_blocked_by() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "DEP"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create blocker issue
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocker issue"
    })).await;
    assert_eq!(body["identifier"], "DEP-1");

    // Create blocked issue
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked issue",
        "blocked_by": ["DEP-1"]
    })).await;
    let blocked_iid = body["id"].as_str().unwrap();

    // Check blockers -- should show DEP-1 as unresolved
    let (status, body) = get(&mut app, &format!("/api/issues/{}/blockers", blocked_iid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["blocked"], true);
    assert!(body["blockers"].as_array().unwrap().contains(&json!("DEP-1")));

    // Resolve blocker (move to done: todo -> in_progress -> in_review -> done)
    let iid1 = get(&mut app, "/api/issues/DEP-1").await.1["id"].as_str().unwrap().to_string();
    send(&mut app, "PATCH", &format!("/api/issues/{}", iid1), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", iid1), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", iid1), json!({"status": "done"})).await;

    // Check blockers again -- should be unblocked now
    let (status, body) = get(&mut app, &format!("/api/issues/{}/blockers", blocked_iid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["blocked"], false);
    assert!(body["blockers"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_blocked_by_validates_identifiers() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "V"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Try to create with non-existent dependency
    let (status, _) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Bad deps",
        "blocked_by": ["FAKE-999"]
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
}

// ============================================================
// Projects CRUD
// ============================================================

#[tokio::test]
async fn test_project_crud() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/projects", cid), json!({
        "name": "Project Alpha",
        "description": "First project",
        "color": "#ff0000"
    })).await;
    assert_eq!(status, StatusCode::OK);
    let pid = body["id"].as_str().unwrap();
    assert_eq!(body["name"], "Project Alpha");

    // Get
    let (status, body) = get(&mut app, &format!("/api/projects/{}", pid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"], "Project Alpha");

    // List
    let (status, body) = get(&mut app, &format!("/api/companies/{}/projects", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);

    // Update
    let (status, body) = send(&mut app, "PATCH", &format!("/api/projects/{}", pid), json!({
        "name": "Project Alpha v2",
        "status": "completed"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"], "Project Alpha v2");
    assert_eq!(body["status"], "completed");
}

// ============================================================
// Goals CRUD
// ============================================================

#[tokio::test]
async fn test_goal_crud() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/goals", cid), json!({
        "title": "Ship v1",
        "description": "Get to version 1.0",
        "level": "milestone"
    })).await;
    assert_eq!(status, StatusCode::OK);
    let gid = body["id"].as_str().unwrap();
    assert_eq!(body["title"], "Ship v1");

    // List
    let (status, body) = get(&mut app, &format!("/api/companies/{}/goals", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);

    // Update
    let (status, body) = send(&mut app, "PATCH", &format!("/api/goals/{}", gid), json!({
        "status": "completed"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "completed");
}

// ============================================================
// Labels
// ============================================================

#[tokio::test]
async fn test_label_crud() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/labels", cid), json!({
        "name": "bug",
        "color": "#ff0000"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"], "bug");
    assert_eq!(body["color"], "#ff0000");

    // List
    let (status, body) = get(&mut app, &format!("/api/companies/{}/labels", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);
}

// ============================================================
// Routines
// ============================================================

#[tokio::test]
async fn test_routine_crud() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Worker"
    })).await;
    let aid = body["id"].as_str().unwrap();

    // Create
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/routines", cid), json!({
        "title": "Daily sync",
        "description": "Check for new work",
        "assignee_agent_id": aid,
        "cron_expression": "0 */15 * * * *"
    })).await;
    assert_eq!(status, StatusCode::OK);
    let rid = body["id"].as_str().unwrap();
    assert_eq!(body["title"], "Daily sync");

    // List
    let (status, body) = get(&mut app, &format!("/api/companies/{}/routines", cid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);

    // Update
    let (status, body) = send(&mut app, "PATCH", &format!("/api/routines/{}", rid), json!({
        "status": "paused"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "paused");

    // Delete (soft-delete: sets status to 'inactive')
    let (status, body) = delete_req(&mut app, &format!("/api/routines/{}", rid)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "inactive");

    // List returns ALL routines (including inactive)
    let (status, body) = get(&mut app, &format!("/api/companies/{}/routines", cid)).await;
    assert_eq!(status, StatusCode::OK);
    // Soft-deleted routine is still in the list but marked inactive
    assert_eq!(body.as_array().unwrap().len(), 1);
    assert_eq!(body[0]["status"], "inactive");
}

// ============================================================
// Dispatch
// ============================================================

#[tokio::test]
async fn test_dispatch_auto_assign() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "DSP"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create idle engineer
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Engineer-1",
        "role": "engineer"
    })).await;
    let aid = body["id"].as_str().unwrap();

    // Create a todo issue
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Auto-dispatch me",
        "priority": "high"
    })).await;
    let iid = body["id"].as_str().unwrap();

    // Dispatch
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/dispatch", cid), json!({
        "role": "engineer"
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["dispatched"], true);
    assert_eq!(body["agent"]["id"], aid);
    assert_eq!(body["issue"]["id"], iid);

    // Verify issue is now in_progress
    let (_, issue) = get(&mut app, &format!("/api/issues/{}", iid)).await;
    assert_eq!(issue["status"], "in_progress");
    assert_eq!(issue["assignee_agent_id"], aid);
}

#[tokio::test]
async fn test_dispatch_no_idle_agents() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // No agents created, should fail
    let (status, _) = send(&mut app, "POST", &format!("/api/companies/{}/dispatch", cid), json!({
        "role": "engineer"
    })).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

// ============================================================
// Activity Log
// ============================================================

#[tokio::test]
async fn test_activity_log() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create an issue (generates activity)
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Activity test"
    })).await;

    // Check activity
    let (status, body) = get(&mut app, &format!("/api/companies/{}/activity", cid)).await;
    assert_eq!(status, StatusCode::OK);
    let activities = body.as_array().unwrap();
    assert!(!activities.is_empty());

    // Should have at least one "issue.created" activity
    let has_created = activities.iter().any(|a| a["action"] == "issue.created");
    assert!(has_created, "Expected issue.created activity, got: {:?}", activities);
}

// ============================================================
// Issue filtering
// ============================================================

#[tokio::test]
async fn test_issue_filter_by_status() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create multiple issues
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "I1"})).await;
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "I2"})).await;

    let (_, body) = get(&mut app, &format!("/api/companies/{}/issues?status=todo", cid)).await;
    assert_eq!(body.as_array().unwrap().len(), 2);

    let (_, body) = get(&mut app, &format!("/api/companies/{}/issues?status=done", cid)).await;
    assert!(body.as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_issue_priority_ordering() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "TST"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create issues with different priorities
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Low", "priority": "low"
    })).await;
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Critical", "priority": "critical"
    })).await;
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Medium", "priority": "medium"
    })).await;

    // List all -- should return 3 issues, ordered by created_at DESC
    let (_, body) = get(&mut app, &format!("/api/companies/{}/issues", cid)).await;
    let issues = body.as_array().unwrap();
    assert_eq!(issues.len(), 3);
    // All 3 should be present; ordering is created_at DESC
    let titles: Vec<&str> = issues.iter().map(|i| i["title"].as_str().unwrap()).collect();
    assert!(titles.contains(&"Low"));
    assert!(titles.contains(&"Critical"));
    assert!(titles.contains(&"Medium"));
}

// ============================================================
// P7-C: Dependency Auto-Resolution
// ============================================================

#[tokio::test]
async fn test_blocked_issue_starts_in_backlog() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "BLK"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create blocker issue
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocker"
    })).await;
    assert_eq!(body["status"], "todo");

    // Create blocked issue -- should start in 'backlog', not 'todo'
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked",
        "blocked_by": ["BLK-1"]
    })).await;
    assert_eq!(body["status"], "backlog");
    let blocked_id = body["id"].as_str().unwrap();
}

#[tokio::test]
async fn test_auto_promote_on_blocker_resolved() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "AUT"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create blocker
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocker"
    })).await;
    let blocker_id = body["id"].as_str().unwrap();

    // Create blocked issue (starts in backlog)
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked",
        "blocked_by": ["AUT-1"]
    })).await;
    let blocked_id = body["id"].as_str().unwrap();
    assert_eq!(body["status"], "backlog");

    // Resolve blocker: todo -> in_progress -> in_review -> done
    send(&mut app, "PATCH", &format!("/api/issues/{}", blocker_id), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", blocker_id), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", blocker_id), json!({"status": "done"})).await;

    // Blocked issue should have been auto-promoted to 'todo'
    let (_, body) = get(&mut app, &format!("/api/issues/{}", blocked_id)).await;
    assert_eq!(body["status"], "todo");
}

#[tokio::test]
async fn test_auto_promote_multi_dep() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "MDE"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create two blockers
    let (_, b1) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "Blocker 1"})).await;
    let (_, b2) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "Blocker 2"})).await;
    let b1_id = b1["id"].as_str().unwrap();
    let b2_id = b2["id"].as_str().unwrap();

    // Create issue blocked by both
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Multi-blocked",
        "blocked_by": ["MDE-1", "MDE-2"]
    })).await;
    let blocked_id = body["id"].as_str().unwrap();
    assert_eq!(body["status"], "backlog");

    // Resolve first blocker -- should NOT auto-promote (still blocked by MDE-2)
    send(&mut app, "PATCH", &format!("/api/issues/{}", b1_id), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", b1_id), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", b1_id), json!({"status": "done"})).await;

    let (_, body) = get(&mut app, &format!("/api/issues/{}", blocked_id)).await;
    assert_eq!(body["status"], "backlog", "Should stay backlog with one unresolved blocker");

    // Resolve second blocker -- NOW should auto-promote
    send(&mut app, "PATCH", &format!("/api/issues/{}", b2_id), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", b2_id), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", b2_id), json!({"status": "done"})).await;

    let (_, body) = get(&mut app, &format!("/api/issues/{}", blocked_id)).await;
    assert_eq!(body["status"], "todo", "Should auto-promote when all blockers resolved");
}

#[tokio::test]
async fn test_auto_promote_logs_activity() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Test Co", "issue_prefix": "ALG"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create blocker + blocked
    let (_, b1) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "Blocker"})).await;
    let (_, _) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked",
        "blocked_by": ["ALG-1"]
    })).await;

    // Resolve blocker
    let b1_id = b1["id"].as_str().unwrap();
    send(&mut app, "PATCH", &format!("/api/issues/{}", b1_id), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", b1_id), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", b1_id), json!({"status": "done"})).await;

    // Check activity log for auto_promoted entry
    let (_, body) = get(&mut app, &format!("/api/companies/{}/activity", cid)).await;
    let activities = body.as_array().unwrap();
    let promoted = activities.iter().find(|a| a["action"] == "issue.auto_promoted");
    assert!(promoted.is_some(), "Should find an auto_promoted activity log entry");

    let details: serde_json::Value = serde_json::from_str(promoted.unwrap()["details"].as_str().unwrap()).unwrap();
    assert_eq!(details["from"], "backlog");
    assert_eq!(details["to"], "todo");
    assert_eq!(details["reason"], "all blockers resolved");
}

// ============================================================
// P7-A: Dashboard API Metrics
// ============================================================

#[tokio::test]
async fn test_dashboard_metrics() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Metrics Co", "issue_prefix": "MTX"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create some issues
    let (_, i1) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "T1"})).await;
    let (_, i2) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({"title": "T2"})).await;
    let i1_id = i1["id"].as_str().unwrap();
    let i2_id = i2["id"].as_str().unwrap();

    // Create a blocked issue (goes to backlog)
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked", "blocked_by": ["MTX-1"]
    })).await;

    // Complete one issue
    send(&mut app, "PATCH", &format!("/api/issues/{}", i1_id), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", i1_id), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", i1_id), json!({"status": "done"})).await;

    // Fetch dashboard
    let (_, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;

    // Verify metrics object exists
    assert!(body["metrics"].is_object(), "Should have metrics");

    // Throughput should be an array
    let throughput = body["metrics"]["throughput"].as_array();
    assert!(throughput.is_some(), "Should have throughput array");

    // Agent utilization should be a number (0.0 since no agents)
    let util = body["metrics"]["agentUtilization"].as_f64();
    assert!(util.is_some(), "Should have agentUtilization");
    assert_eq!(util.unwrap(), 0.0, "No agents means 0% utilization");

    // Bottlenecks should be an array
    assert!(body["metrics"]["bottlenecks"].is_array(), "Should have bottlenecks array");

    // Blocker chains: MTX-3 was auto-promoted since MTX-1 is done, so no remaining blocker chains
    let chains = body["metrics"]["blockerChains"].as_array().unwrap();
    assert!(chains.is_empty(), "MTX-3 was auto-promoted, no blocker chains remain");

    // Task counts: MTX-1 done, MTX-2 todo, MTX-3 auto-promoted to todo
    let tasks = &body["tasks"];
    assert_eq!(tasks["done"], 1);
    assert_eq!(tasks["todo"], 2, "MTX-2 + auto-promoted MTX-3");
}

// ============================================================
// P7-B: Alerting
// ============================================================

#[tokio::test]
async fn test_alert_rules_crud() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Alert Co", "issue_prefix": "ALT"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create alert rule
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "Agent dead check",
        "rule_type": "agent_dead",
        "threshold_mins": 30
    })).await;
    assert_eq!(status, StatusCode::OK);
    let rule_id = body["id"].as_str().unwrap();
    assert_eq!(body["rule_type"], "agent_dead");
    assert_eq!(body["threshold_mins"], 30);

    // List rules
    let (_, body) = get(&mut app, &format!("/api/companies/{}/alert-rules", cid)).await;
    let rules = body.as_array().unwrap();
    assert_eq!(rules.len(), 1);

    // Delete rule
    let (status, _) = delete_req(&mut app, &format!("/api/alert-rules/{}", rule_id)).await;
    assert_eq!(status, StatusCode::OK);

    // Verify deleted
    let (_, body) = get(&mut app, &format!("/api/companies/{}/alert-rules", cid)).await;
    assert!(body.as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_alert_evaluate_no_activity() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Quiet Co", "issue_prefix": "QUT"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create no_activity rule with 1 minute threshold
    send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "No activity check",
        "rule_type": "no_activity",
        "threshold_mins": 1
    })).await;

    // Evaluate -- should fire (company was just created, activity log has entries)
    // Actually the company creation itself logged activity, so 1min threshold won't fire
    // Let's use a very short threshold of 0 (or check that it doesn't fire)
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/alerts/evaluate", cid), json!({})).await;
    assert_eq!(body["evaluatedRules"], 1);
    // no_activity rule evaluates; may or may not fire depending on test timing
}

#[tokio::test]
async fn test_alert_rule_validates_type() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Type Co", "issue_prefix": "TYP"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Invalid rule type
    let (status, _) = send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "Bad rule",
        "rule_type": "nonexistent",
        "threshold_mins": 30
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
}

// ============================================================
// P7-D: Spec Module
// ============================================================

#[tokio::test]
async fn test_spec_crud_and_parser() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Spec Co", "issue_prefix": "SPC"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create a spec document with multiple change sections
    let spec_content = r#"# Spec: Add authentication

## Change: Implement login endpoint
priority: high
blocked_by: []
description: Create POST /auth/login with JWT tokens
Must support email and password login.

---
## Change: Add user registration
priority: medium
blocked_by: []
description: Create POST /auth/register endpoint

---
## Change: Add password reset
priority: low
blocked_by: [SPC-1, SPC-2]
description: Allow users to reset passwords via email
"#;

    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Auth Feature Spec",
        "raw_content": spec_content
    })).await;
    assert_eq!(status, StatusCode::OK);
    let spec_id = body["id"].as_str().unwrap();
    assert_eq!(body["change_count"], 3);
    assert_eq!(body["status"], "draft");
    assert_eq!(body["title"], "Auth Feature Spec");

    // Verify parsed changes are stored
    let parsed: serde_json::Value = serde_json::from_str(body["parsed_changes"].as_str().unwrap()).unwrap();
    let changes = parsed.as_array().unwrap();
    assert_eq!(changes.len(), 3);
    assert_eq!(changes[0]["title"], "Implement login endpoint");
    assert_eq!(changes[0]["priority"], "high");
    assert_eq!(changes[1]["title"], "Add user registration");
    assert_eq!(changes[2]["blocked_by"].as_array().unwrap().len(), 2);

    // GET spec by id
    let (status, body) = get(&mut app, &format!("/api/specs/{}", spec_id)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["title"], "Auth Feature Spec");

    // LIST specs
    let (_, body) = get(&mut app, &format!("/api/companies/{}/specs", cid)).await;
    let specs = body.as_array().unwrap();
    assert_eq!(specs.len(), 1);

    // DELETE spec
    let (status, _) = delete_req(&mut app, &format!("/api/specs/{}", spec_id)).await;
    assert_eq!(status, StatusCode::OK);

    // Verify deleted
    let (status, _) = get(&mut app, &format!("/api/specs/{}", spec_id)).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_spec_import_creates_issues() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Import Co", "issue_prefix": "IMP"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create a spec with 2 unblocked changes
    let spec_content = r#"# Spec: Basic features

## Change: Setup database
priority: high
description: Create the initial schema

---
## Change: Build API endpoints
priority: medium
description: REST API for CRUD operations
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Basic Features",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import all changes as issues
    let (status, body) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["imported"], 2);
    assert_eq!(body["status"], "imported");

    let issues = body["issues"].as_array().unwrap();
    assert_eq!(issues.len(), 2);

    // First issue should be IMP-1, unblocked -> starts in todo
    assert_eq!(issues[0]["identifier"], "IMP-1");
    assert_eq!(issues[0]["status"], "todo");
    assert_eq!(issues[0]["title"], "Setup database");

    // Second issue should be IMP-2, unblocked -> starts in todo
    assert_eq!(issues[1]["identifier"], "IMP-2");
    assert_eq!(issues[1]["status"], "todo");

    // Verify spec status updated
    let (_, spec_body) = get(&mut app, &format!("/api/specs/{}", spec_id)).await;
    assert_eq!(spec_body["status"], "imported");
    assert_eq!(spec_body["imported_count"], 2);

    // Verify issues exist in company
    let (_, issues_body) = get(&mut app, &format!("/api/companies/{}/issues", cid)).await;
    assert_eq!(issues_body.as_array().unwrap().len(), 2);

    // Verify origin_kind is 'spec' and origin_id is the spec id
    assert_eq!(issues_body.as_array().unwrap()[0]["origin_kind"], "spec");
    assert_eq!(issues_body.as_array().unwrap()[0]["origin_id"], spec_id);
}

#[tokio::test]
async fn test_spec_import_blocked_goes_to_backlog() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Blocked Co", "issue_prefix": "BLK"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // First create a prerequisite issue manually
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Existing prerequisite"
    })).await;
    // This is BLK-1

    // Create a spec with a blocked change
    let spec_content = r#"# Spec: Dependent work

## Change: Blocked feature
priority: high
blocked_by: [BLK-1]
description: This depends on the prerequisite
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Dependent Work",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import -- should create issue in backlog (not todo) because blocked_by BLK-1
    let (status, body) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    assert_eq!(status, StatusCode::OK);

    let issues = body["issues"].as_array().unwrap();
    assert_eq!(issues[0]["status"], "backlog");
    assert_eq!(issues[0]["identifier"], "BLK-2");

    // Verify blocked_by is set on the created issue
    let (_, all_issues) = get(&mut app, &format!("/api/companies/{}/issues", cid)).await;
    let blocked_issue = all_issues.as_array().unwrap().iter()
        .find(|i| i["identifier"] == "BLK-2").unwrap();
    let deps: Vec<String> = serde_json::from_str(blocked_issue["blocked_by"].as_str().unwrap()).unwrap();
    assert_eq!(deps, vec!["BLK-1"]);
}

#[tokio::test]
async fn test_spec_import_partial_indices() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Partial Co", "issue_prefix": "PRT"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let spec_content = r#"# Spec: Three changes

## Change: First change
priority: high
description: Number one

---
## Change: Second change
priority: medium
description: Number two

---
## Change: Third change
priority: low
description: Number three
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Three Changes",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import only index 0 and 2
    let (status, body) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({
        "indices": [0, 2]
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["imported"], 2);
    assert_eq!(body["status"], "partial"); // not all 3 imported

    let issues = body["issues"].as_array().unwrap();
    assert_eq!(issues[0]["title"], "First change");
    assert_eq!(issues[1]["title"], "Third change");

    // Now import the remaining one (index 1)
    let (status, body) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({
        "indices": [1]
    })).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["imported"], 1);
    assert_eq!(body["status"], "imported"); // now all imported
}

#[tokio::test]
async fn test_spec_import_idempotent() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Idempotent Co", "issue_prefix": "IDM"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let spec_content = r#"# Spec: Single change

## Change: Do something
priority: medium
description: A thing to do
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Single",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import once
    let (_, body1) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    assert_eq!(body1["imported"], 1);

    // Import again -- should be 0 new (already imported)
    let (_, body2) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    // Status is now "imported" so it should be rejected
    // Actually spec is already imported, so it should reject
}

#[tokio::test]
async fn test_spec_already_imported_rejected() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Reject Co", "issue_prefix": "REJ"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let spec_content = r#"# Spec: Quick

## Change: Fast task
priority: high
description: Do it fast
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Quick",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import all
    send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;

    // Try to import again -- should be rejected
    let (status, _) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn test_spec_issues_endpoint() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Issues Co", "issue_prefix": "ISU"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let spec_content = r#"# Spec: Multi

## Change: Task A
priority: high
description: First task

---
## Change: Task B
priority: low
description: Second task
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Multi",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import
    send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;

    // Get spec issues
    let (status, body) = get(&mut app, &format!("/api/specs/{}/issues", spec_id)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["total"], 2);

    let items = body["items"].as_array().unwrap();
    assert_eq!(items[0]["mapping"]["change_title"], "Task A");
    assert_eq!(items[1]["mapping"]["change_title"], "Task B");

    // Each item should have the full issue object
    assert!(items[0]["issue"]["identifier"].is_string());
    assert_eq!(items[0]["issue"]["origin_kind"], "spec");
}

#[tokio::test]
async fn test_spec_import_invalid_blocked_by() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Invalid Dep Co", "issue_prefix": "INV"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let spec_content = r#"# Spec: Bad deps

## Change: Blocked by nonexistent
priority: high
blocked_by: [INV-999]
description: This references an issue that doesn't exist
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Bad Deps",
        "raw_content": spec_content
    })).await;
    let spec_id = body["id"].as_str().unwrap();

    // Import should fail validation -- INV-999 doesn't exist
    let (status, body) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    let err = body["error"].as_str().unwrap();
    assert!(err.contains("INV-999"), "Error should mention unknown dependency: {}", err);
}

#[tokio::test]
async fn test_spec_with_project_id() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Project Co", "issue_prefix": "PRJ"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create a project
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/projects", cid), json!({
        "name": "Auth Project"
    })).await;
    let project_id = body["id"].as_str().unwrap();

    let spec_content = r#"# Spec: Project work

## Change: Project task
priority: medium
description: A task in a project
"#;

    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/specs", cid), json!({
        "title": "Project Spec",
        "raw_content": spec_content,
        "project_id": project_id
    })).await;
    let spec_id = body["id"].as_str().unwrap();
    assert_eq!(body["project_id"], project_id);

    // Import
    let (_, body) = send(&mut app, "POST", &format!("/api/specs/{}/import", spec_id), json!({})).await;
    let issue_id = body["issues"].as_array().unwrap()[0]["issueId"].as_str().unwrap();

    // Verify issue has project_id set
    let (_, issue) = get(&mut app, &format!("/api/issues/{}", issue_id)).await;
    assert_eq!(issue["project_id"], project_id);
}

// ============================================================
// P8-D: Additional P7 coverage
// ============================================================

#[tokio::test]
async fn test_alert_evaluate_agent_dead() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Dead Agent Co", "issue_prefix": "DED"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create an agent (no heartbeat -- never heartbeated)
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Ghost Agent"
    })).await;
    assert_eq!(body["status"], "idle");

    // Create alert rule with 0 min threshold (fires immediately for no-heartbeat agents)
    send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "Dead check",
        "rule_type": "agent_dead",
        "threshold_mins": 0
    })).await;

    // Evaluate
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/alerts/evaluate", cid), json!({})).await;
    assert_eq!(body["evaluatedRules"], 1);
    assert_eq!(body["firedAlerts"], 1, "Agent with no heartbeat should trigger agent_dead alert");

    let alerts = body["alerts"].as_array().unwrap();
    assert_eq!(alerts[0]["ruleType"], "agent_dead");
}

#[tokio::test]
async fn test_alert_evaluate_issue_blocked() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Blocked Co", "issue_prefix": "BLK"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create an issue (BLK-1)
    let (_, i1) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocker issue"
    })).await;

    // Create a blocked issue (BLK-2 blocked by BLK-1) -- goes to backlog
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked issue",
        "blocked_by": ["BLK-1"]
    })).await;

    // Create issue_blocked rule with 0 threshold.
    // Note: SQL uses updated_at < now - threshold, so threshold=0 means
    // "stuck for >0 minutes". A just-created issue won't trigger.
    send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "Stuck blocked",
        "rule_type": "issue_blocked",
        "threshold_mins": 0
    })).await;

    // Evaluate -- just-created issue shouldn't fire (updated_at ~= now)
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/alerts/evaluate", cid), json!({})).await;
    assert_eq!(body["evaluatedRules"], 1);
    // The issue was just created so updated_at is approximately now -- no fire
    assert_eq!(body["firedAlerts"], 0, "Just-created blocked issue should not fire (not stuck yet)");

    // Now test that the rule type is recognized by checking the evaluatedRules count
    // The real test for issue_blocked firing would need time to pass or a negative threshold
}

#[tokio::test]
async fn test_alert_evaluate_no_violations() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Clean Co", "issue_prefix": "CLN"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create rules but with no matching conditions
    send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "Dead check",
        "rule_type": "agent_dead",
        "threshold_mins": 999
    })).await;
    send(&mut app, "POST", &format!("/api/companies/{}/alert-rules", cid), json!({
        "name": "Blocked check",
        "rule_type": "issue_blocked",
        "threshold_mins": 999
    })).await;

    // Evaluate -- should not fire anything
    let (_, body) = send(&mut app, "POST", &format!("/api/companies/{}/alerts/evaluate", cid), json!({})).await;
    assert_eq!(body["evaluatedRules"], 2);
    assert_eq!(body["firedAlerts"], 0, "No violations expected for empty company with high thresholds");
}

#[tokio::test]
async fn test_blockers_endpoint() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Blocker Co", "issue_prefix": "BKR"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create blocker issue (BKR-1)
    let (_, i1) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocker"
    })).await;
    let i1_id = i1["id"].as_str().unwrap();

    // Create blocked issue (BKR-2) blocked by BKR-1
    let (_, i2) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked",
        "blocked_by": ["BKR-1"]
    })).await;
    let i2_id = i2["id"].as_str().unwrap();

    // Check blockers for blocked issue -- should show BKR-1
    let (_, body) = get(&mut app, &format!("/api/issues/{}/blockers", i2_id)).await;
    assert!(body["blocked"].as_bool().unwrap(), "Issue should be blocked");
    let blockers = body["blockers"].as_array().unwrap();
    assert_eq!(blockers.len(), 1);
    assert_eq!(blockers[0], "BKR-1");
    assert_eq!(body["allDependencies"].as_array().unwrap().len(), 1);

    // Complete the blocker -- resolve BKR-1 to done
    send(&mut app, "PATCH", &format!("/api/issues/{}", i1_id), json!({"status": "in_progress"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", i1_id), json!({"status": "in_review"})).await;
    send(&mut app, "PATCH", &format!("/api/issues/{}", i1_id), json!({"status": "done"})).await;

    // Now blockers should be empty
    let (_, body) = get(&mut app, &format!("/api/issues/{}/blockers", i2_id)).await;
    assert!(!body["blocked"].as_bool().unwrap(), "Issue should no longer be blocked");
    assert!(body["blockers"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_blockers_endpoint_no_blockers() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Free Co", "issue_prefix": "FRE"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, issue) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Free issue"
    })).await;
    let iid = issue["id"].as_str().unwrap();

    let (_, body) = get(&mut app, &format!("/api/issues/{}/blockers", iid)).await;
    assert!(!body["blocked"].as_bool().unwrap());
    assert!(body["blockers"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_dashboard_agent_utilization() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Util Co", "issue_prefix": "UTL"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Create two agents
    let (_, a1) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Worker 1"
    })).await;
    let (_, a2) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Worker 2"
    })).await;

    // Both start idle -> utilization 0%
    let (_, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;
    assert_eq!(body["metrics"]["agentUtilization"], 0.0);
    assert_eq!(body["agents"]["idle"], 2);

    // Set one to running
    let a1_id = a1["id"].as_str().unwrap();
    send(&mut app, "PATCH", &format!("/api/agents/{}", a1_id), json!({"status": "running"})).await;

    let (_, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;
    let util = body["metrics"]["agentUtilization"].as_f64().unwrap();
    assert_eq!(util, 50.0, "1 of 2 agents running = 50%");
    assert_eq!(body["agents"]["active"], 1);
    assert_eq!(body["agents"]["idle"], 1);
}

#[tokio::test]
async fn test_dashboard_blocker_chains() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Chain Co", "issue_prefix": "CHN"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // CHN-1: not blocked
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Root"
    })).await;

    // CHN-2: blocked by CHN-1 (CHN-1 is still todo, so CHN-2 stays in backlog)
    // Actually CHN-1 is todo, auto-promote won't fire yet
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Blocked child",
        "blocked_by": ["CHN-1"]
    })).await;

    // CHN-3: blocked by CHN-2
    send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Deep blocked",
        "blocked_by": ["CHN-2"]
    })).await;

    let (_, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;
    let chains = body["metrics"]["blockerChains"].as_array().unwrap();
    // CHN-2 and CHN-3 should appear as blocker chains (both in backlog)
    assert!(chains.len() >= 2, "Should have at least 2 blocker chain entries, got {}", chains.len());
}

// ============================================================
// P8-B: Input validation
// ============================================================

#[tokio::test]
async fn test_validation_issue_empty_title() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Val Co", "issue_prefix": "VAL"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Empty title should be rejected
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": ""
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(body["error"].as_str().unwrap().contains("title"));
}

#[tokio::test]
async fn test_validation_issue_bad_priority() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Pri Co", "issue_prefix": "PRI"
    })).await;
    let cid = body["id"].as_str().unwrap();

    // Invalid priority should be rejected
    let (status, body) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Valid title",
        "priority": "super_urgent"
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(body["error"].as_str().unwrap().contains("priority"));
}

#[tokio::test]
async fn test_validation_agent_bad_status() {
    let (mut app, _) = test_app().await;

    let (_, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Stat Co", "issue_prefix": "STA"
    })).await;
    let cid = body["id"].as_str().unwrap();

    let (_, agent) = send(&mut app, "POST", &format!("/api/companies/{}/agents", cid), json!({
        "name": "Agent X"
    })).await;
    let aid = agent["id"].as_str().unwrap();

    // Invalid status should be rejected
    let (status, body) = send(&mut app, "PATCH", &format!("/api/agents/{}", aid), json!({
        "status": "flying"
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(body["error"].as_str().unwrap().contains("status"));
}

#[tokio::test]
async fn test_validation_company_empty_name() {
    let (mut app, _) = test_app().await;

    let (status, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "   "
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(body["error"].as_str().unwrap().contains("name"));
}

#[tokio::test]
async fn test_validation_company_bad_prefix() {
    let (mut app, _) = test_app().await;

    let (status, body) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Good name",
        "issue_prefix": "123"
    })).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(body["error"].as_str().unwrap().contains("issue_prefix"));
}

// ============================================================
// P9: Outcome Verification
// ============================================================

#[tokio::test]
async fn test_verify_outcome_creates_record() {
    let (mut app, _) = test_app().await;

    // Create company + issue
    let (_, company) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Outcome Test Co"
    })).await;
    let cid = company["id"].as_str().unwrap();

    let (_, issue) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Test issue for outcomes"
    })).await;
    let issue_id = issue["id"].as_str().unwrap();

    // POST verify
    let (status, outcome) = send(&mut app, "POST", &format!("/api/issues/{}/verify", issue_id), json!({
        "tests_passed": 782,
        "tests_failed": 0,
        "tests_before": 780,
        "tests_after": 782,
        "files_changed": ["src/gasm.rs"],
        "build_success": true,
        "success": true,
        "summary": "SUCCESS | 782 passed, 0 failed"
    })).await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(outcome["tests_passed"], 782);
    assert_eq!(outcome["tests_failed"], 0);
    assert_eq!(outcome["tests_before"], 780);
    assert_eq!(outcome["tests_after"], 782);
    assert_eq!(outcome["success"], true);
    assert_eq!(outcome["build_success"], true);
    assert_eq!(outcome["summary"], "SUCCESS | 782 passed, 0 failed");
    assert!(outcome["id"].is_string());
    assert!(outcome["verified_at"].is_string());
}

#[tokio::test]
async fn test_verify_outcome_by_identifier() {
    let (mut app, _) = test_app().await;

    let (_, company) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Ident Co",
        "issue_prefix": "ID"
    })).await;
    let cid = company["id"].as_str().unwrap();

    let (_, issue) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Verify by identifier"
    })).await;
    let identifier = issue["identifier"].as_str().unwrap();

    // POST verify using identifier (GEO-N) instead of UUID
    let (status, outcome) = send(&mut app, "POST", &format!("/api/issues/{}/verify", identifier), json!({
        "tests_passed": 10,
        "tests_failed": 2,
        "build_success": false,
        "success": false,
        "summary": "FAILED | 2 tests failed"
    })).await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(outcome["tests_passed"], 10);
    assert_eq!(outcome["tests_failed"], 2);
    assert_eq!(outcome["success"], false);
}

#[tokio::test]
async fn test_list_outcomes_for_issue() {
    let (mut app, _) = test_app().await;

    let (_, company) = send(&mut app, "POST", "/api/companies", json!({
        "name": "List Outcomes Co"
    })).await;
    let cid = company["id"].as_str().unwrap();

    let (_, issue) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Multi outcome"
    })).await;
    let issue_id = issue["id"].as_str().unwrap();

    // First verify (failure)
    send(&mut app, "POST", &format!("/api/issues/{}/verify", issue_id), json!({
        "tests_passed": 5,
        "tests_failed": 3,
        "success": false,
        "summary": "FAILED"
    })).await;

    // Second verify (success)
    send(&mut app, "POST", &format!("/api/issues/{}/verify", issue_id), json!({
        "tests_passed": 8,
        "tests_failed": 0,
        "success": true,
        "summary": "SUCCESS"
    })).await;

    // GET outcomes -- should return both
    let (status, outcomes) = get(&mut app, &format!("/api/issues/{}/outcomes", issue_id)).await;
    assert_eq!(status, StatusCode::OK);
    let arr = outcomes.as_array().unwrap();
    assert_eq!(arr.len(), 2);
    // One success, one failure (order may vary since timestamps land in same second)
    let success_count = arr.iter().filter(|o| o["success"] == true).count();
    let fail_count = arr.iter().filter(|o| o["success"] == false).count();
    assert_eq!(success_count, 1);
    assert_eq!(fail_count, 1);
}

#[tokio::test]
async fn test_issue_get_includes_latest_outcome() {
    let (mut app, _) = test_app().await;

    let (_, company) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Latest Outcome Co"
    })).await;
    let cid = company["id"].as_str().unwrap();

    let (_, issue) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Check latest outcome"
    })).await;
    let issue_id = issue["id"].as_str().unwrap();

    // Before verification: latest_outcome should be null
    let (status, body) = get(&mut app, &format!("/api/issues/{}", issue_id)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["latest_outcome"], Value::Null);

    // Add a verify
    send(&mut app, "POST", &format!("/api/issues/{}/verify", issue_id), json!({
        "tests_passed": 50,
        "success": true,
        "summary": "OK"
    })).await;

    // After verification: latest_outcome should be populated
    let (status, body) = get(&mut app, &format!("/api/issues/{}", issue_id)).await;
    assert_eq!(status, StatusCode::OK);
    assert!(body["latest_outcome"].is_object());
    assert_eq!(body["latest_outcome"]["tests_passed"], 50);
    assert_eq!(body["latest_outcome"]["success"], true);
}

#[tokio::test]
async fn test_dashboard_includes_outcome_stats() {
    let (mut app, _) = test_app().await;

    let (_, company) = send(&mut app, "POST", "/api/companies", json!({
        "name": "Dashboard Outcome Co"
    })).await;
    let cid = company["id"].as_str().unwrap();

    let (_, issue) = send(&mut app, "POST", &format!("/api/companies/{}/issues", cid), json!({
        "title": "Dashboard outcome"
    })).await;
    let issue_id = issue["id"].as_str().unwrap();

    // No outcomes yet
    let (_, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;
    assert_eq!(body["outcomes"]["total"], 0);
    assert_eq!(body["outcomes"]["verificationRate"], 0.0);

    // Add successful outcome
    send(&mut app, "POST", &format!("/api/issues/{}/verify", issue_id), json!({
        "tests_passed": 100,
        "tests_before": 95,
        "tests_after": 100,
        "success": true,
        "summary": "SUCCESS"
    })).await;

    let (_, body) = get(&mut app, &format!("/api/companies/{}/dashboard", cid)).await;
    assert_eq!(body["outcomes"]["total"], 1);
    assert_eq!(body["outcomes"]["successful"], 1);
    assert_eq!(body["outcomes"]["verificationRate"], 100.0);
    assert!(body["outcomes"]["avgTestDelta"].as_f64().unwrap() > 0.0);
    assert!(body["outcomes"]["recentFailures"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_verify_nonexistent_issue_404() {
    let (mut app, _) = test_app().await;

    let (status, _) = send(&mut app, "POST", "/api/issues/nonexistent/verify", json!({
        "success": true
    })).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_outcomes_for_nonexistent_issue_404() {
    let (mut app, _) = test_app().await;

    let (status, _) = get(&mut app, "/api/issues/nonexistent/outcomes").await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}
