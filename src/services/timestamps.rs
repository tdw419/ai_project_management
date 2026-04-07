/// Parse a timestamp string that may be in RFC3339 or SQLite datetime format.
///
/// SQLite's `datetime('now')` produces `"2026-04-07 12:00:00"`.
/// RFC3339 is `"2026-04-07T12:00:00Z"`.
/// This function handles both, treating non-RFC3339 strings as UTC naive datetimes.
use chrono::{DateTime, NaiveDateTime, TimeZone, Utc};

pub fn parse_timestamp(s: &str) -> Option<DateTime<Utc>> {
    // Try RFC3339 first (the format we now store)
    if let Ok(dt) = DateTime::parse_from_rfc3339(s) {
        return Some(dt.to_utc());
    }
    // Fall back to SQLite datetime format: "YYYY-MM-DD HH:MM:SS"
    if let Ok(naive) = NaiveDateTime::parse_from_str(s, "%Y-%m-%d %H:%M:%S") {
        return Some(Utc.from_utc_datetime(&naive));
    }
    // Also try the "T" variant without timezone
    if let Ok(naive) = NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S") {
        return Some(Utc.from_utc_datetime(&naive));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rfc3339() {
        let dt = parse_timestamp("2026-04-07T12:00:00Z").unwrap();
        assert_eq!(dt.format("%Y-%m-%d").to_string(), "2026-04-07");
    }

    #[test]
    fn test_sqlite_datetime() {
        let dt = parse_timestamp("2026-04-07 12:00:00").unwrap();
        assert_eq!(dt.format("%Y-%m-%d").to_string(), "2026-04-07");
    }

    #[test]
    fn test_invalid() {
        assert!(parse_timestamp("not a date").is_none());
    }
}
