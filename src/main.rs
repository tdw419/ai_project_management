use geo_forge::config::Config;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let config = Config::load()?;

    // Initialize logging based on config
    let env_filter = config.logging.level.clone();
    match config.logging.format.as_str() {
        "json" => {
            tracing_subscriber::fmt()
                .json()
                .with_env_filter(env_filter)
                .init();
        }
        _ => {
            tracing_subscriber::fmt()
                .with_env_filter(env_filter)
                .init();
        }
    }

    tracing::info!(
        db_path = %config.server.db_path,
        port = config.server.port,
        "GeoForge starting"
    );

    let connection_string = if config.server.db_path.starts_with("sqlite:") {
        config.server.db_path.clone()
    } else {
        format!("sqlite:{}?mode=rwc", config.server.db_path)
    };

    let pool = sqlx::SqlitePool::connect(&connection_string).await?;

    sqlx::query("PRAGMA journal_mode=WAL")
        .execute(&pool)
        .await?;
    sqlx::query("PRAGMA foreign_keys=ON")
        .execute(&pool)
        .await?;
    // SQLite busy timeout: wait up to 5 seconds for locks before SQLITE_BUSY
    sqlx::query("PRAGMA busy_timeout=5000")
        .execute(&pool)
        .await?;

    sqlx::migrate!("./migrations")
        .run(&pool)
        .await?;

    let state = std::sync::Arc::new(geo_forge::AppState::new(pool));

    // Start background services
    let health_state = state.clone();
    let health_cfg = config.health.clone();
    tokio::spawn(async move {
        geo_forge::services::health_monitor::run_health_monitor(health_state, &health_cfg).await;
    });

    let scheduler_state = state.clone();
    let scheduler_interval = config.scheduler.interval_secs;
    tokio::spawn(async move {
        geo_forge::services::scheduler::run_scheduler(scheduler_state, scheduler_interval).await;
    });

    let rate_max = config.rate_limit.max;
    let rate_refill = config.rate_limit.refill_per_sec;

    let limiter = geo_forge::middleware::rate_limit::RateLimitLayer::new(rate_max, rate_refill)
        .limiter().clone();
    tokio::spawn(geo_forge::middleware::rate_limit::run_prune_task(
        limiter, 60, 300,
    ));

    tracing::info!(
        max = rate_max,
        refill = rate_refill,
        "Rate limiter configured"
    );

    let app = geo_forge::app::build_router(state, rate_max, rate_refill, &config.cors.origins);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", config.server.port)).await?;
    tracing::info!("GeoForge listening on port {}", config.server.port);

    let shutdown = async {
        if tokio::signal::ctrl_c().await.is_err() {
            tracing::warn!("Ctrl+C handler failed, shutting down immediately");
        } else {
            tracing::info!("Shutdown signal received, draining connections...");
        }
    };

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown)
        .await?;

    tracing::info!("GeoForge shut down cleanly");
    Ok(())
}
