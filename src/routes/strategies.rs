use axum::{extract::{Path, State}, response::Json};
use sqlx::query_as;
use crate::{AppError, AppResult, SharedState};
use crate::db::models::{PromptTemplate, UpdatePromptTemplateRequest};

/// GET /api/strategies -- list all strategies and their prompt templates.
pub async fn list(
    State(state): State<SharedState>,
) -> AppResult<Json<Vec<PromptTemplate>>> {
    let templates = query_as::<_, PromptTemplate>(
        "SELECT * FROM prompt_templates ORDER BY strategy"
    )
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(templates))
}

/// GET /api/strategies/{name}/prompt -- get the prompt template for a specific strategy.
pub async fn get_prompt(
    State(state): State<SharedState>,
    Path(name): Path<String>,
) -> AppResult<Json<PromptTemplate>> {
    // Validate strategy name
    if !crate::db::models::STRATEGIES.contains(&name.as_str()) {
        return Err(AppError::Validation(format!(
            "Unknown strategy '{}'. Valid: {}",
            name,
            crate::db::models::STRATEGIES.join(", ")
        )));
    }

    let template = query_as::<_, PromptTemplate>(
        "SELECT * FROM prompt_templates WHERE strategy = ?"
    )
        .bind(&name)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("No prompt template for strategy '{}'", name)))?;

    Ok(Json(template))
}

/// PATCH /api/strategies/{name}/prompt -- update a strategy's prompt template.
pub async fn update_prompt(
    State(state): State<SharedState>,
    Path(name): Path<String>,
    Json(body): Json<UpdatePromptTemplateRequest>,
) -> AppResult<Json<PromptTemplate>> {
    if !crate::db::models::STRATEGIES.contains(&name.as_str()) {
        return Err(AppError::Validation(format!(
            "Unknown strategy '{}'. Valid: {}",
            name,
            crate::db::models::STRATEGIES.join(", ")
        )));
    }

    if let Some(ref prompt) = body.prompt {
        crate::validation::require_non_empty(prompt, "prompt")?;
    }

    // Build update query dynamically
    let template = query_as::<_, PromptTemplate>(
        "SELECT * FROM prompt_templates WHERE strategy = ?"
    )
        .bind(&name)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("No prompt template for strategy '{}'", name)))?;

    let new_prompt = body.prompt.unwrap_or(template.prompt);
    let new_description = body.description.unwrap_or(template.description);

    sqlx::query(
        "UPDATE prompt_templates SET prompt = ?, description = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE strategy = ?"
    )
        .bind(&new_prompt)
        .bind(&new_description)
        .bind(&name)
        .execute(&state.pool)
        .await?;

    let updated = query_as::<_, PromptTemplate>(
        "SELECT * FROM prompt_templates WHERE strategy = ?"
    )
        .bind(&name)
        .fetch_one(&state.pool)
        .await?;

    Ok(Json(updated))
}
