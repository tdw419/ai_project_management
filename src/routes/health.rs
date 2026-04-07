use axum::response::Json;

pub async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "ok",
        "service": "geo-forge",
        "version": env!("CARGO_PKG_VERSION"),
    }))
}
