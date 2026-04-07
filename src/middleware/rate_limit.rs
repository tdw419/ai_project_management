use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use axum::extract::Request;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use tokio::sync::Mutex;
use tower::{Layer, Service};

/// Token-bucket rate limiter per client IP.
#[derive(Clone)]
pub struct RateLimiter {
    buckets: Arc<Mutex<HashMap<String, TokenBucket>>>,
    max_tokens: u32,
    refill_per_second: u32,
}

struct TokenBucket {
    tokens: f64,
    last_refill: Instant,
}

impl RateLimiter {
    pub fn new(max_tokens: u32, refill_per_second: u32) -> Self {
        Self {
            buckets: Arc::new(Mutex::new(HashMap::new())),
            max_tokens,
            refill_per_second,
        }
    }

    /// Check if a request from this key is allowed. Returns true if allowed.
    pub async fn allow(&self, key: &str) -> bool {
        let mut buckets = self.buckets.lock().await;
        let now = Instant::now();

        let bucket = buckets.entry(key.to_string()).or_insert_with(|| TokenBucket {
            tokens: self.max_tokens as f64,
            last_refill: now,
        });

        // Refill tokens based on elapsed time
        let elapsed = now.duration_since(bucket.last_refill).as_secs_f64();
        bucket.tokens = (bucket.tokens + elapsed * self.refill_per_second as f64)
            .min(self.max_tokens as f64);
        bucket.last_refill = now;

        if bucket.tokens >= 1.0 {
            bucket.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    /// Prune buckets that haven't been used recently (periodic cleanup).
    pub async fn prune_stale(&self, max_age_secs: u64) {
        let mut buckets = self.buckets.lock().await;
        let now = Instant::now();
        buckets.retain(|_, bucket| {
            now.duration_since(bucket.last_refill).as_secs() < max_age_secs
        });
    }
}

#[derive(Clone)]
pub struct RateLimitLayer {
    limiter: RateLimiter,
}

impl RateLimitLayer {
    pub fn new(max_tokens: u32, refill_per_second: u32) -> Self {
        Self {
            limiter: RateLimiter::new(max_tokens, refill_per_second),
        }
    }

    pub fn limiter(&self) -> &RateLimiter {
        &self.limiter
    }
}

impl<S> Layer<S> for RateLimitLayer {
    type Service = RateLimitMiddleware<S>;

    fn layer(&self, inner: S) -> Self::Service {
        RateLimitMiddleware {
            inner,
            limiter: self.limiter.clone(),
        }
    }
}

#[derive(Clone)]
pub struct RateLimitMiddleware<S> {
    inner: S,
    limiter: RateLimiter,
}

impl<S> Service<Request> for RateLimitMiddleware<S>
where
    S: tower::Service<Request, Response = Response, Error = std::convert::Infallible> + Clone + Send + 'static,
    S::Future: Send + 'static,
{
    type Response = Response;
    type Error = std::convert::Infallible;
    type Future = std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send + 'static>>;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.inner.poll_ready(cx)
    }

    fn call(&mut self, request: Request) -> Self::Future {
        let limiter = self.limiter.clone();
        let mut inner = self.inner.clone();

        Box::pin(async move {
            let client_key = extract_client_key(&request);

            if !limiter.allow(&client_key).await {
                tracing::warn!(client = %client_key, "Rate limit exceeded");
                let body = serde_json::json!({
                    "error": "Rate limit exceeded",
                    "retry_after": "1s"
                });
                let response = (
                    StatusCode::TOO_MANY_REQUESTS,
                    axum::Json(body),
                ).into_response();
                return Ok(response);
            }

            inner.call(request).await
        })
    }
}

fn extract_client_key(request: &Request) -> String {
    if let Some(xff) = request.headers().get("x-forwarded-for") {
        if let Ok(val) = xff.to_str() {
            if let Some(first) = val.split(',').next() {
                return first.trim().to_string();
            }
        }
    }
    if let Some(xri) = request.headers().get("x-real-ip") {
        if let Ok(val) = xri.to_str() {
            return val.trim().to_string();
        }
    }
    "unknown".to_string()
}

/// Background task to prune stale rate limit buckets periodically.
pub async fn run_prune_task(limiter: RateLimiter, interval_secs: u64, max_age_secs: u64) {
    let mut interval = tokio::time::interval(
        std::time::Duration::from_secs(interval_secs)
    );
    loop {
        interval.tick().await;
        limiter.prune_stale(max_age_secs).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;

    #[tokio::test]
    async fn test_rate_limiter_allows_within_budget() {
        let limiter = RateLimiter::new(5, 1);
        for _ in 0..5 {
            assert!(limiter.allow("test-client").await);
        }
        assert!(!limiter.allow("test-client").await);
    }

    #[tokio::test]
    async fn test_rate_limiter_different_clients_independent() {
        let limiter = RateLimiter::new(2, 1);
        assert!(limiter.allow("client-a").await);
        assert!(limiter.allow("client-a").await);
        assert!(!limiter.allow("client-a").await);
        assert!(limiter.allow("client-b").await);
    }

    #[tokio::test]
    async fn test_rate_limiter_refills() {
        let limiter = RateLimiter::new(1, 1000);
        assert!(limiter.allow("test").await);
        assert!(!limiter.allow("test").await);
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        assert!(limiter.allow("test").await);
    }

    #[tokio::test]
    async fn test_prune_stale() {
        let limiter = RateLimiter::new(5, 1);
        limiter.allow("old-client").await;
        limiter.allow("new-client").await;
        limiter.prune_stale(0).await;
        let buckets = limiter.buckets.lock().await;
        assert!(buckets.is_empty());
    }

    #[test]
    fn test_extract_client_key_forwarded() {
        let req = Request::builder()
            .header("x-forwarded-for", "1.2.3.4, 5.6.7.8")
            .body(Body::empty())
            .unwrap();
        assert_eq!(extract_client_key(&req), "1.2.3.4");
    }

    #[test]
    fn test_extract_client_key_real_ip() {
        let req = Request::builder()
            .header("x-real-ip", "10.0.0.1")
            .body(Body::empty())
            .unwrap();
        assert_eq!(extract_client_key(&req), "10.0.0.1");
    }

    #[test]
    fn test_extract_client_key_fallback() {
        let req = Request::builder()
            .body(Body::empty())
            .unwrap();
        assert_eq!(extract_client_key(&req), "unknown");
    }
}
