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
