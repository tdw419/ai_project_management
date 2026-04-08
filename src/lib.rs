pub mod app;
pub mod config;
pub mod db;
pub mod error;
pub mod middleware;
pub mod routes;
pub mod services;
pub mod state_machine;
pub mod validation;

use std::sync::Arc;
use sqlx::SqlitePool;
use sqlx::sqlite::SqliteQueryResult;

pub use error::{AppError, AppResult};

pub struct AppState {
    pub pool: SqlitePool,
    pub event_bus: Option<crate::services::event_bus::EventBus>,
}

impl AppState {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool, event_bus: None }
    }

    pub fn with_event_bus(mut self, bus: crate::services::event_bus::EventBus) -> Self {
        self.event_bus = Some(bus);
        self
    }

    /// Execute a write query with automatic SQLITE_BUSY retry.
    /// SQLite is single-writer; under concurrent access from harness workers,
    /// writes can fail with SQLITE_BUSY. This retries with exponential backoff.
    pub async fn execute_write<'q, F, Fut>(&self, f: F) -> Result<SqliteQueryResult, sqlx::Error>
    where
        F: Fn(sqlx::pool::PoolConnection<sqlx::Sqlite>) -> Fut,
        Fut: std::future::Future<Output = Result<SqliteQueryResult, sqlx::Error>>,
    {
        let mut attempts = 0u32;
        let max_attempts = 5;
        loop {
            let conn = self.pool.acquire().await?;
            match f(conn).await {
                Ok(result) => return Ok(result),
                Err(e) => {
                    if attempts >= max_attempts - 1 {
                        return Err(e);
                    }
                    if is_busy_error(&e) {
                        attempts += 1;
                        let delay = std::time::Duration::from_millis(50 * 2u64.pow(attempts));
                        tracing::warn!(attempts, delay_ms = delay.as_millis(), "SQLITE_BUSY, retrying");
                        tokio::time::sleep(delay).await;
                    } else {
                        return Err(e);
                    }
                }
            }
        }
    }
}

fn is_busy_error(e: &sqlx::Error) -> bool {
    match e {
        sqlx::Error::Database(db_err) => {
            // SQLite BUSY error code is 5
            db_err.code().map_or(false, |c| c == "5" || c == "SQLITE_BUSY")
        }
        _ => false,
    }
}

pub type SharedState = Arc<AppState>;
