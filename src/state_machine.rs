use crate::error::AppError;

/// Valid issue status transitions.
/// Enforces that you can't skip states (e.g., backlog -> done).
pub fn validate_transition(current: &str, target: &str) -> Result<(), AppError> {
    let valid = match current {
        "backlog" => matches!(target, "todo" | "cancelled"),
        "todo" => matches!(target, "in_progress" | "backlog" | "cancelled"),
        "in_progress" => matches!(target, "in_review" | "todo" | "cancelled"),
        "in_review" => matches!(target, "done" | "in_progress" | "cancelled"),
        "done" => matches!(target, "todo"), // reopen
        "cancelled" => matches!(target, "todo"), // reopen
        _ => false,
    };

    if valid {
        Ok(())
    } else {
        Err(AppError::InvalidTransition {
            from: current.to_string(),
            to: target.to_string(),
            id: String::new(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_happy_path() {
        assert!(validate_transition("backlog", "todo").is_ok());
        assert!(validate_transition("todo", "in_progress").is_ok());
        assert!(validate_transition("in_progress", "in_review").is_ok());
        assert!(validate_transition("in_review", "done").is_ok());
    }

    #[test]
    fn test_reopen() {
        assert!(validate_transition("done", "todo").is_ok());
        assert!(validate_transition("cancelled", "todo").is_ok());
    }

    #[test]
    fn test_reject_invalid() {
        assert!(validate_transition("backlog", "done").is_err());
        assert!(validate_transition("backlog", "in_progress").is_err());
        assert!(validate_transition("todo", "done").is_err());
        assert!(validate_transition("done", "in_progress").is_err());
    }

    #[test]
    fn test_cancel_from_any_open() {
        assert!(validate_transition("backlog", "cancelled").is_ok());
        assert!(validate_transition("todo", "cancelled").is_ok());
        assert!(validate_transition("in_progress", "cancelled").is_ok());
        assert!(validate_transition("in_review", "cancelled").is_ok());
    }

    #[test]
    fn test_qa_reject() {
        assert!(validate_transition("in_review", "in_progress").is_ok());
    }
}
