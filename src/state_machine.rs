use crate::error::AppError;

/// Valid issue status transitions.
/// When qa_gate is enabled, in_progress -> done is rejected (must go through in_review).
pub fn validate_transition(current: &str, target: &str, qa_gate: bool) -> Result<(), AppError> {
    let valid = match current {
        "backlog" => matches!(target, "todo" | "cancelled"),
        "todo" => matches!(target, "in_progress" | "backlog" | "cancelled"),
        "in_progress" => {
            if qa_gate {
                matches!(target, "in_review" | "todo" | "cancelled")
            } else {
                matches!(target, "in_review" | "done" | "todo" | "cancelled")
            }
        }
        "in_review" => matches!(target, "done" | "in_progress" | "cancelled"),
        "done" => matches!(target, "todo"), // reopen
        "cancelled" => matches!(target, "todo"), // reopen
        _ => false,
    };

    if valid {
        Ok(())
    } else {
        let reason = if qa_gate && current == "in_progress" && target == "done" {
            " (QA gate requires in_review before done)".to_string()
        } else {
            String::new()
        };
        Err(AppError::InvalidTransition {
            from: current.to_string(),
            to: target.to_string() + &reason,
            id: String::new(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_happy_path() {
        assert!(validate_transition("backlog", "todo", true).is_ok());
        assert!(validate_transition("todo", "in_progress", true).is_ok());
        assert!(validate_transition("in_progress", "in_review", true).is_ok());
        assert!(validate_transition("in_review", "done", true).is_ok());
    }

    #[test]
    fn test_reopen() {
        assert!(validate_transition("done", "todo", true).is_ok());
        assert!(validate_transition("cancelled", "todo", true).is_ok());
    }

    #[test]
    fn test_reject_invalid() {
        assert!(validate_transition("backlog", "done", true).is_err());
        assert!(validate_transition("backlog", "in_progress", true).is_err());
        assert!(validate_transition("todo", "done", true).is_err());
        assert!(validate_transition("done", "in_progress", true).is_err());
    }

    #[test]
    fn test_cancel_from_any_open() {
        assert!(validate_transition("backlog", "cancelled", true).is_ok());
        assert!(validate_transition("todo", "cancelled", true).is_ok());
        assert!(validate_transition("in_progress", "cancelled", true).is_ok());
        assert!(validate_transition("in_review", "cancelled", true).is_ok());
    }

    #[test]
    fn test_qa_reject() {
        // With QA gate on, can't skip from in_progress to done
        assert!(validate_transition("in_progress", "done", true).is_err());
        // Can still go to in_review
        assert!(validate_transition("in_progress", "in_review", true).is_ok());
    }

    #[test]
    fn test_qa_gate_off() {
        // Without QA gate, in_progress -> done is allowed
        assert!(validate_transition("in_progress", "done", false).is_ok());
    }
}
