use axum::Router;
use axum::routing::{delete, get, patch, post};
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;

use crate::SharedState;

pub fn build_router(state: SharedState, rate_max: u32, rate_refill: u32, cors_origins: &str) -> Router {
    let cors = build_cors_layer(cors_origins);

    let rate_layer = crate::middleware::rate_limit::RateLimitLayer::new(rate_max, rate_refill);

    Router::new()
        // Health
        .route("/api/health", get(crate::routes::health::health))
        // Metrics
        .route("/api/metrics", get(crate::routes::metrics::metrics))
        // Stats
        .route("/api/stats", get(crate::routes::stats::stats))
        // Companies
        .route("/api/companies", get(crate::routes::companies::list).post(crate::routes::companies::create))
        .route("/api/companies/{cid}", get(crate::routes::companies::get))
        .route("/api/companies/{cid}/dashboard", get(crate::routes::companies::dashboard))
        // Agents
        .route("/api/companies/{cid}/agents", get(crate::routes::agents::list))
        .route("/api/agents/{aid}", get(crate::routes::agents::get))
        .route("/api/companies/{cid}/agents", post(crate::routes::agents::create))
        .route("/api/companies/{cid}/agents/register", post(crate::routes::agents::register))
        .route("/api/agents/{aid}", patch(crate::routes::agents::update))
        .route("/api/agents/{aid}", delete(crate::routes::agents::delete))
        .route("/api/agents/{aid}/wakeup", post(crate::routes::agents::wakeup))
        .route("/api/agents/{aid}/invoke", post(crate::routes::agents::invoke))
        .route("/api/agents/{aid}/heartbeat", post(crate::routes::agents::heartbeat))
        // Issues
        .route("/api/companies/{cid}/issues", get(crate::routes::issues::list))
        .route("/api/issues/{iid}", get(crate::routes::issues::get))
        .route("/api/companies/{cid}/issues", post(crate::routes::issues::create))
        .route("/api/issues/{iid}", patch(crate::routes::issues::update))
        .route("/api/issues/{iid}", delete(crate::routes::issues::delete))
        .route("/api/issues/{iid}/checkout", post(crate::routes::issues::checkout))
        .route("/api/issues/{iid}/comments", get(crate::routes::issues::list_comments))
        .route("/api/issues/{iid}/comments", post(crate::routes::issues::create_comment))
        .route("/api/issues/{iid}/blockers", get(crate::routes::issues::blockers))
        // Projects
        .route("/api/companies/{cid}/projects", get(crate::routes::projects::list))
        .route("/api/projects/{pid}", get(crate::routes::projects::get))
        .route("/api/companies/{cid}/projects", post(crate::routes::projects::create))
        .route("/api/projects/{pid}", patch(crate::routes::projects::update))
        // Goals
        .route("/api/companies/{cid}/goals", get(crate::routes::goals::list))
        .route("/api/companies/{cid}/goals", post(crate::routes::goals::create))
        .route("/api/goals/{gid}", patch(crate::routes::goals::update))
        // Labels
        .route("/api/companies/{cid}/labels", get(crate::routes::labels::list))
        .route("/api/companies/{cid}/labels", post(crate::routes::labels::create))
        // Routines
        .route("/api/companies/{cid}/routines", get(crate::routes::routines::list))
        .route("/api/companies/{cid}/routines", post(crate::routes::routines::create))
        .route("/api/routines/{rid}", patch(crate::routes::routines::update))
        .route("/api/routines/{rid}", delete(crate::routes::routines::delete))
        .route("/api/routines/{rid}/trigger", post(crate::routes::routines::trigger))
        .route("/api/routines/{rid}/runs", get(crate::routes::routines::list_runs))
        // Dispatch
        .route("/api/companies/{cid}/dispatch", post(crate::routes::dispatch::dispatch))
        // Activity log
        .route("/api/companies/{cid}/activity", get(crate::routes::activity::list))
        // Alert rules
        .route("/api/companies/{cid}/alert-rules", get(crate::routes::alerts::list).post(crate::routes::alerts::create))
        .route("/api/alert-rules/{rid}", delete(crate::routes::alerts::delete))
        .route("/api/companies/{cid}/alerts/evaluate", post(crate::routes::alerts::evaluate))
        // Spec documents
        .route("/api/companies/{cid}/specs", get(crate::routes::specs::list).post(crate::routes::specs::create))
        .route("/api/specs/{sid}", get(crate::routes::specs::get).delete(crate::routes::specs::delete))
        .route("/api/specs/{sid}/import", post(crate::routes::specs::import))
        .route("/api/specs/{sid}/issues", get(crate::routes::specs::spec_issues))
        // Middleware layers (order matters: outermost first)
        .layer(cors)
        .layer(TraceLayer::new_for_http())
        .layer(rate_layer)
        .with_state(state)
}

/// Build a CORS layer from config string.
/// Empty string = allow all origins (dev-friendly default).
/// Otherwise, comma-separated list of allowed origin URLs.
fn build_cors_layer(origins: &str) -> CorsLayer {
    if origins.is_empty() {
        CorsLayer::permissive()
    } else {
        let allowed: Vec<_> = origins
            .split(',')
            .filter_map(|s| {
                let trimmed = s.trim();
                trimmed.parse().ok()
            })
            .collect();

        if allowed.is_empty() {
            CorsLayer::permissive()
        } else {
            CorsLayer::new()
                .allow_origin(allowed)
                .allow_methods(Any)
                .allow_headers(Any)
        }
    }
}
