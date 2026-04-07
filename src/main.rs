use std::sync::Arc;

use axum::Router;
use axum::routing::{get, post, patch};
use sqlx::SqlitePool;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

mod db;
mod routes;
mod services;
mod error;
mod state_machine;

pub use error::{AppError, AppResult};

pub struct AppState {
    pub pool: SqlitePool,
}

impl AppState {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }
}

pub type SharedState = Arc<AppState>;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter("geo_forge=debug,sqlx=warn")
        .init();

    let db_path = std::env::var("GEOFORGE_DB")
        .unwrap_or_else(|_| "geo_forge.db".to_string());

    let connection_string = if db_path.starts_with("sqlite:") {
        db_path
    } else {
        format!("sqlite:{}?mode=rwc", db_path)
    };

    tracing::info!("Connecting to {}", connection_string);

    let pool = SqlitePool::connect(&connection_string)
        .await?;

    // Enable WAL mode and foreign keys
    sqlx::query("PRAGMA journal_mode=WAL")
        .execute(&pool)
        .await?;
    sqlx::query("PRAGMA foreign_keys=ON")
        .execute(&pool)
        .await?;

    // Run migrations
    let schema = include_str!("../migrations/001_init.sql");
    sqlx::raw_sql(schema).execute(&pool).await?;
    let invocations_schema = include_str!("../migrations/002_invocations.sql");
    sqlx::raw_sql(invocations_schema).execute(&pool).await?;

    let state = Arc::new(AppState::new(pool));

    // Start background services
    let health_state = state.clone();
    tokio::spawn(async move {
        services::health_monitor::run_health_monitor(health_state).await;
    });

    let scheduler_state = state.clone();
    tokio::spawn(async move {
        services::scheduler::run_scheduler(scheduler_state).await;
    });

    let app = Router::new()
        // Health
        .route("/api/health", get(routes::health::health))
        // Companies
        .route("/api/companies", get(routes::companies::list).post(routes::companies::create))
        .route("/api/companies/{cid}", get(routes::companies::get))
        .route("/api/companies/{cid}/dashboard", get(routes::companies::dashboard))
        // Agents
        .route("/api/companies/{cid}/agents", get(routes::agents::list))
        .route("/api/agents/{aid}", get(routes::agents::get))
        .route("/api/companies/{cid}/agents", post(routes::agents::create))
        .route("/api/agents/{aid}", patch(routes::agents::update))
        .route("/api/agents/{aid}/wakeup", post(routes::agents::wakeup))
        .route("/api/agents/{aid}/invoke", post(routes::agents::invoke))
        .route("/api/agents/{aid}/heartbeat", post(routes::agents::heartbeat))
        // Issues
        .route("/api/companies/{cid}/issues", get(routes::issues::list))
        .route("/api/issues/{iid}", get(routes::issues::get))
        .route("/api/companies/{cid}/issues", post(routes::issues::create))
        .route("/api/issues/{iid}", patch(routes::issues::update))
        .route("/api/issues/{iid}/checkout", post(routes::issues::checkout))
        .route("/api/issues/{iid}/comments", get(routes::issues::list_comments))
        .route("/api/issues/{iid}/comments", post(routes::issues::create_comment))
        .route("/api/issues/{iid}/blockers", get(routes::issues::blockers))
        // Projects
        .route("/api/companies/{cid}/projects", get(routes::projects::list))
        .route("/api/projects/{pid}", get(routes::projects::get))
        .route("/api/companies/{cid}/projects", post(routes::projects::create))
        .route("/api/projects/{pid}", patch(routes::projects::update))
        // Goals
        .route("/api/companies/{cid}/goals", get(routes::goals::list))
        .route("/api/companies/{cid}/goals", post(routes::goals::create))
        .route("/api/goals/{gid}", patch(routes::goals::update))
        // Labels
        .route("/api/companies/{cid}/labels", get(routes::labels::list))
        .route("/api/companies/{cid}/labels", post(routes::labels::create))
        // Routines
        .route("/api/companies/{cid}/routines", get(routes::routines::list))
        .route("/api/companies/{cid}/routines", post(routes::routines::create))
        .route("/api/routines/{rid}", patch(routes::routines::update))
        .route("/api/routines/{rid}/trigger", post(routes::routines::trigger))
        // Dispatch
        .route("/api/companies/{cid}/dispatch", post(routes::dispatch::dispatch))
        // Activity log
        .route("/api/companies/{cid}/activity", get(routes::activity::list))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let port: u16 = std::env::var("GEOFORGE_PORT")
        .unwrap_or_else(|_| "3101".to_string())
        .parse()
        .unwrap_or(3101);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", port)).await?;
    tracing::info!("GeoForge listening on port {}", port);
    axum::serve(listener, app).await?;

    Ok(())
}
