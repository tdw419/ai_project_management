/**
 * Model router -- decides which model to use for a task.
 *
 * Replaces AIPM v2's model_router.py. Much simpler now:
 * - Default to cloud model (proven to work)
 * - Fall back to local if cloud keeps failing for a project
 * - Escalate to cloud after N local failures
 */

import type { ProjectConfig } from '../models/config.js';
import type { Strategy } from '../models/outcome.js';

interface RouterState {
  /** Recent outcomes for this project */
  recentOutcomes: ('success' | 'failure')[];
  /** Model override for this project */
  modelOverride?: string;
}

const projectStates = new Map<string, RouterState>();

export interface RoutingDecision {
  model: string;
  reason: string;
}

/**
 * Select the best model for a task.
 *
 * Rules (simplified from v2's 6-rule engine):
 * 1. If cloud has >60% success rate recently, use cloud
 * 2. If this is attempt 3+ and we're on local, escalate to cloud
 * 3. Otherwise use the project's preferred model
 */
export function selectModel(
  project: ProjectConfig,
  strategy: Strategy,
  attemptNumber: number,
  defaultCloud: string,
  defaultLocal: string,
): RoutingDecision {
  const state = getOrCreateState(project.name);
  const outcomes = state.recentOutcomes;
  const cloudSuccessRate = calcSuccessRate(outcomes);

  // Rule 1: Cloud model for retry attempts >= 3
  if (attemptNumber >= 3) {
    return {
      model: defaultCloud,
      reason: `Attempt ${attemptNumber} >= 3, escalating to cloud`,
    };
  }

  // Rule 2: If cloud is working, stay on cloud
  if (cloudSuccessRate > 0.5 && outcomes.length >= 2) {
    return {
      model: defaultCloud,
      reason: `Cloud success rate ${(cloudSuccessRate * 100).toFixed(0)}% > 50%`,
    };
  }

  // Rule 3: Default to cloud for spec-driven tasks (they need the quality)
  return {
    model: defaultCloud,
    reason: 'Default cloud for spec-driven tasks',
  };
}

/**
 * Record an outcome for future routing decisions.
 */
export function recordOutcome(
  projectName: string,
  success: boolean,
): void {
  const state = getOrCreateState(projectName);
  state.recentOutcomes.push(success ? 'success' : 'failure');
  // Keep last 10 outcomes
  if (state.recentOutcomes.length > 10) {
    state.recentOutcomes.shift();
  }
}

function getOrCreateState(name: string): RouterState {
  if (!projectStates.has(name)) {
    projectStates.set(name, { recentOutcomes: [] });
  }
  return projectStates.get(name)!;
}

function calcSuccessRate(outcomes: ('success' | 'failure')[]): number {
  if (outcomes.length === 0) return 0;
  const successes = outcomes.filter(o => o === 'success').length;
  return successes / outcomes.length;
}
