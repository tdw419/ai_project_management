/**
 * Transform Pipeline Runner
 *
 * Executes registered transforms in deterministic order (phase, then priority)
 * on skill and command content during artifact generation.
 *
 * Usage:
 *   import { TransformPipeline } from './transform-pipeline.js';
 *   const pipeline = new TransformPipeline();
 *   const result = pipeline.run('skill', content, { toolId: 'opencode', workflowId: 'explore' });
 */

export type {
  Transform,
  TransformScope,
  TransformPhase,
  TransformContext,
  TransformResult,
} from './transform-types.js';
import type {
  Transform,
  TransformScope,
  TransformContext,
  TransformResult,
} from './transform-types.js';

// ---------------------------------------------------------------------------
// Built-in transforms
// ---------------------------------------------------------------------------

import { transformToHyphenCommands } from '../../utils/command-references.js';

/**
 * OpenCode hyphen-command rewrite transform.
 *
 * OpenCode uses hyphen-based command references (/opsx-new) instead of
 * colon-based (/opsx:new). This transform rewrites skill instructions
 * for OpenCode compatibility.
 */
export const openCodeHyphenTransform: Transform = {
  id: 'opencode-hyphen-commands',
  description: 'Rewrite /opsx: references to /opsx- for OpenCode compatibility',
  scope: 'skill',
  phase: 'preWrite',
  priority: 100,
  applies: (ctx: TransformContext): boolean => ctx.toolId === 'opencode',
  transform: (content: string): string => transformToHyphenCommands(content),
};

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

/**
 * The transform pipeline. Holds a registry of transforms and executes them
 * in deterministic order.
 */
export class TransformPipeline {
  private readonly transforms: Transform[] = [];

  constructor() {
    // Register built-in transforms
    this.transforms.push(openCodeHyphenTransform);
  }

  /**
   * Register an additional transform. Useful for extensibility and testing.
   */
  register(transform: Transform): void {
    this.transforms.push(transform);
  }

  /**
   * Run all applicable transforms for the given scope and context.
   * Returns the transformed content and the list of applied transform IDs.
   */
  run(
    scope: TransformScope,
    content: string,
    ctx: TransformContext,
  ): TransformResult {
    const applicable = this.getApplicable(scope, ctx);
    const appliedTransforms: string[] = [];
    let current = content;

    for (const t of applicable) {
      current = t.transform(current, ctx);
      appliedTransforms.push(t.id);
    }

    return { content: current, appliedTransforms };
  }

  /**
   * Run transforms only for 'skill' scope (convenience method).
   */
  runForSkill(
    content: string,
    ctx: TransformContext,
  ): TransformResult {
    return this.run('skill', content, ctx);
  }

  /**
   * Run transforms only for 'command' scope (convenience method).
   */
  runForCommand(
    content: string,
    ctx: TransformContext,
  ): TransformResult {
    return this.run('command', content, ctx);
  }

  /**
   * Returns all transforms that apply for the given scope and context,
   * sorted by phase then priority (deterministic order).
   */
  getApplicable(scope: TransformScope, ctx: TransformContext): Transform[] {
    const phaseOrder: Record<string, number> = {
      preAdapter: 0,
      postAdapter: 1,
      preWrite: 2,
    };

    return this.transforms
      .filter((t) => {
        // Scope match: 'both' always matches, otherwise exact match
        if (t.scope !== 'both' && t.scope !== scope) return false;
        // Context match: does the transform apply for this tool/workflow?
        return t.applies(ctx);
      })
      .sort((a, b) => {
        const phaseDiff = phaseOrder[a.phase] - phaseOrder[b.phase];
        if (phaseDiff !== 0) return phaseDiff;
        return a.priority - b.priority;
      });
  }

  /**
   * Get all registered transforms (for testing/debugging).
   */
  getAll(): readonly Transform[] {
    return this.transforms;
  }
}

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

let _instance: TransformPipeline | null = null;

/**
 * Returns the shared transform pipeline instance.
 * Memoized after first call.
 */
export function getTransformPipeline(): TransformPipeline {
  if (!_instance) {
    _instance = new TransformPipeline();
  }
  return _instance;
}

/**
 * Resets the singleton pipeline instance.
 * Useful for tests that need a fresh pipeline.
 */
export function resetTransformPipeline(): void {
  _instance = null;
}
