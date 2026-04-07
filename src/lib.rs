pub mod app;
pub mod config;
pub mod db;
pub mod error;
pub mod middleware;
pub mod routes;
pub mod services;
pub mod state_machine;

use std::sync::Arc;
use sqlx::SqlitePool;

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
