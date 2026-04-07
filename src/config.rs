use serde::Deserialize;

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct Config {
    pub server: ServerConfig,
    pub rate_limit: RateLimitConfig,
    pub scheduler: SchedulerConfig,
    pub health: HealthConfig,
    pub logging: LoggingConfig,
    pub cors: CorsConfig,
}

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct ServerConfig {
    pub port: u16,
    pub db_path: String,
}

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct RateLimitConfig {
    pub max: u32,
    pub refill_per_sec: u32,
}

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct SchedulerConfig {
    pub interval_secs: u64,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(default)]
pub struct HealthConfig {
    pub check_interval_secs: u64,
    pub stale_threshold_secs: u64,
    pub dead_threshold_secs: u64,
}

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct LoggingConfig {
    /// "text" or "json"
    pub format: String,
    /// tracing env-filter string, e.g. "geo_forge=debug,sqlx=warn"
    pub level: String,
}

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct CorsConfig {
    /// Empty = allow all origins. Comma-separated URLs otherwise.
    pub origins: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            server: ServerConfig::default(),
            rate_limit: RateLimitConfig::default(),
            scheduler: SchedulerConfig::default(),
            health: HealthConfig::default(),
            logging: LoggingConfig::default(),
            cors: CorsConfig::default(),
        }
    }
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self { port: 3101, db_path: "geo_forge.db".into() }
    }
}

impl Default for RateLimitConfig {
    fn default() -> Self {
        Self { max: 100, refill_per_sec: 10 }
    }
}

impl Default for SchedulerConfig {
    fn default() -> Self {
        Self { interval_secs: 30 }
    }
}

impl Default for HealthConfig {
    fn default() -> Self {
        Self {
            check_interval_secs: 60,
            stale_threshold_secs: 300,
            dead_threshold_secs: 1800,
        }
    }
}

impl Default for LoggingConfig {
    fn default() -> Self {
        Self {
            format: "text".into(),
            level: "geo_forge=debug,sqlx=warn".into(),
        }
    }
}

impl Default for CorsConfig {
    fn default() -> Self {
        Self { origins: String::new() }
    }
}

impl Config {
    /// Load config from file, then override with env vars.
    ///
    /// Lookup order:
    ///   1. `GEOFORGE_CONFIG` env var for file path (default: `geo-forge.toml`)
    ///   2. If file exists, parse it
    ///   3. Override individual fields from GEOFORGE_* env vars
    ///   4. If no file, use defaults + env vars
    pub fn load() -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let config_path = std::env::var("GEOFORGE_CONFIG")
            .unwrap_or_else(|_| "geo-forge.toml".into());

        let mut config = match std::fs::read_to_string(&config_path) {
            Ok(content) => {
                tracing::info!("Loading config from {}", config_path);
                toml::from_str(&content)?
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                tracing::info!("No config file at {}, using defaults", config_path);
                Config::default()
            }
            Err(e) => {
                return Err(format!("Failed to read {}: {}", config_path, e).into());
            }
        };

        // Env var overrides (highest priority)
        apply_env_override("GEOFORGE_DB", &mut config.server.db_path);
        apply_env_parse("GEOFORGE_PORT", &mut config.server.port);
        apply_env_parse("GEOFORGE_RATE_MAX", &mut config.rate_limit.max);
        apply_env_parse("GEOFORGE_RATE_REFILL", &mut config.rate_limit.refill_per_sec);
        apply_env_override("GEOFORGE_CORS_ORIGINS", &mut config.cors.origins);
        apply_env_parse("GEOFORGE_SCHEDULER_INTERVAL", &mut config.scheduler.interval_secs);
        apply_env_parse("GEOFORGE_HEALTH_INTERVAL", &mut config.health.check_interval_secs);
        apply_env_parse("GEOFORGE_STALE_SECS", &mut config.health.stale_threshold_secs);
        apply_env_parse("GEOFORGE_DEAD_SECS", &mut config.health.dead_threshold_secs);

        Ok(config)
    }
}

fn apply_env_override(key: &str, target: &mut String) {
    if let Ok(val) = std::env::var(key) {
        *target = val;
    }
}

fn apply_env_parse<T: std::str::FromStr>(key: &str, target: &mut T) {
    if let Ok(val) = std::env::var(key) {
        if let Ok(parsed) = val.parse() {
            *target = parsed;
        }
    }
}
