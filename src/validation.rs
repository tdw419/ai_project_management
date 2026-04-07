//! Input validation helpers for GeoForge API requests.

use crate::error::AppError;

// -- String length limits --

pub const MAX_TITLE_LEN: usize = 512;
pub const MAX_NAME_LEN: usize = 256;
pub const MAX_DESCRIPTION_LEN: usize = 10_000;
pub const MAX_COMMENT_LEN: usize = 10_000;
pub const MAX_SPEC_CONTENT_LEN: usize = 100_000;
pub const MAX_PREFIX_LEN: usize = 10;

// -- Allowed enum values --

pub const VALID_PRIORITIES: &[&str] = &["critical", "high", "medium", "low"];
pub const VALID_ISSUE_STATUSES: &[&str] = &["backlog", "todo", "in_progress", "in_review", "done", "cancelled"];
pub const VALID_AGENT_STATUSES: &[&str] = &["idle", "running", "paused", "error"];
pub const VALID_AGENT_ROLES: &[&str] = &["engineer", "qa", "ceo", "rusteng", "general"];
pub const VALID_ALERT_TYPES: &[&str] = &["agent_dead", "issue_blocked", "no_activity"];
pub const VALID_CONCURRENCY: &[&str] = &["skip_if_active", "parallel", "replace"];
pub const VALID_ROUTINE_STATUSES: &[&str] = &["active", "paused"];

// -- Validators --

/// Validate a required string field is non-empty and within length limits.
pub fn require_non_empty(value: &str, field: &str) -> Result<(), AppError> {
    if value.trim().is_empty() {
        return Err(AppError::Validation(format!("{} must not be empty", field)));
    }
    Ok(())
}

/// Validate a string field's length. Empty is allowed (use require_non_empty for required fields).
pub fn validate_length(value: &str, field: &str, max_len: usize) -> Result<(), AppError> {
    if value.len() > max_len {
        return Err(AppError::Validation(format!(
            "{} must be at most {} characters (got {})",
            field, max_len, value.len()
        )));
    }
    Ok(())
}

/// Validate an optional string field's length if present.
pub fn validate_opt_length(value: &Option<String>, field: &str, max_len: usize) -> Result<(), AppError> {
    if let Some(ref v) = value {
        validate_length(v, field, max_len)?;
    }
    Ok(())
}

/// Validate that a value is one of the allowed enum values.
pub fn validate_enum(value: &str, field: &str, allowed: &[&str]) -> Result<(), AppError> {
    if !allowed.contains(&value) {
        return Err(AppError::Validation(format!(
            "Invalid {} '{}'. Must be one of: {}",
            field, value, allowed.join(", ")
        )));
    }
    Ok(())
}

/// Validate an optional enum field.
pub fn validate_opt_enum(value: &Option<String>, field: &str, allowed: &[&str]) -> Result<(), AppError> {
    if let Some(ref v) = value {
        validate_enum(v, field, allowed)?;
    }
    Ok(())
}

/// Validate a company issue prefix: alphanumeric, short.
pub fn validate_prefix(value: &str) -> Result<(), AppError> {
    require_non_empty(value, "issue_prefix")?;
    validate_length(value, "issue_prefix", MAX_PREFIX_LEN)?;
    if !value.chars().all(|c| c.is_ascii_alphabetic()) {
        return Err(AppError::Validation(
            "issue_prefix must contain only letters (A-Z)".to_string()
        ));
    }
    Ok(())
}

/// Validate an optional prefix.
pub fn validate_opt_prefix(value: &Option<String>) -> Result<(), AppError> {
    if let Some(ref v) = value {
        validate_prefix(v)?;
    }
    Ok(())
}

/// Validate a webhook URL if present.
pub fn validate_opt_webhook_url(value: &Option<String>) -> Result<(), AppError> {
    if let Some(ref url) = value {
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return Err(AppError::Validation(
                "webhook_url must start with http:// or https://".to_string()
            ));
        }
        validate_length(url, "webhook_url", 2048)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_require_non_empty() {
        assert!(require_non_empty("hello", "field").is_ok());
        assert!(require_non_empty("", "field").is_err());
        assert!(require_non_empty("   ", "field").is_err());
    }

    #[test]
    fn test_validate_length() {
        assert!(validate_length("short", "field", 100).is_ok());
        let long = "x".repeat(101);
        assert!(validate_length(&long, "field", 100).is_err());
    }

    #[test]
    fn test_validate_enum_valid() {
        assert!(validate_enum("medium", "priority", VALID_PRIORITIES).is_ok());
        assert!(validate_enum("critical", "priority", VALID_PRIORITIES).is_ok());
    }

    #[test]
    fn test_validate_enum_invalid() {
        let result = validate_enum("urgent", "priority", VALID_PRIORITIES);
        assert!(result.is_err());
        let msg = result.unwrap_err().to_string();
        assert!(msg.contains("urgent"));
        assert!(msg.contains("critical"));
    }

    #[test]
    fn test_validate_prefix() {
        assert!(validate_prefix("GEO").is_ok());
        assert!(validate_prefix("MTX").is_ok());
        assert!(validate_prefix("123").is_err());
        assert!(validate_prefix("GE-O").is_err());
        assert!(validate_prefix("").is_err());
        assert!(validate_prefix("VERYLONGPREFIX").is_err());
    }

    #[test]
    fn test_validate_webhook_url() {
        assert!(validate_opt_webhook_url(&Some("https://hooks.example.com/x".to_string())).is_ok());
        assert!(validate_opt_webhook_url(&Some("ftp://bad.com".to_string())).is_err());
        assert!(validate_opt_webhook_url(&None).is_ok());
    }
}
