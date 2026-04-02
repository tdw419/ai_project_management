/**
 * Transform Pipeline Types
 *
 * Defines the interfaces for the transform pipeline that applies
 * ordered, deterministic transformations to skill and command content
 * during artifact generation.
 *
 * Transforms are registered with a scope (what they apply to),
 * a phase (when they run relative to adapter rendering),
 * and a priority (ordering within a phase).
 */

/**
 * What artifact types a transform applies to.
 */
export type TransformScope = 'skill' | 'command' | 'both';

/**
 * When a transform runs relative to adapter rendering.
 * - preAdapter: before the adapter renders the command template
 * - postAdapter: after the adapter has rendered (not currently used for skills)
 * - preWrite: just before writing to disk (applies to both skills and commands)
 */
export type TransformPhase = 'preAdapter' | 'postAdapter' | 'preWrite';

/**
 * Context passed to a transform's `applies` and `transform` functions.
 */
export interface TransformContext {
  /** The tool ID (e.g., 'claude', 'opencode') */
  toolId: string;
  /** The workflow ID (e.g., 'explore', 'apply') */
  workflowId: string;
}

/**
 * A single transform in the pipeline.
 *
 * Transforms are pure functions: they take content and context, and return
 * transformed content. They must be deterministic and side-effect-free.
 */
export interface Transform {
  /** Unique identifier for this transform */
  id: string;
  /** Human-readable description */
  description: string;
  /** What artifact types this transform applies to */
  scope: TransformScope;
  /** When this transform runs in the pipeline */
  phase: TransformPhase;
  /** Numeric priority for ordering within a phase (lower runs first) */
  priority: number;
  /** Returns true if this transform should run for the given context */
  applies: (ctx: TransformContext) => boolean;
  /** Applies the transform to the given content */
  transform: (content: string, ctx: TransformContext) => string;
}

/**
 * Result of running the transform pipeline on a single artifact.
 */
export interface TransformResult {
  /** The transformed content */
  content: string;
  /** IDs of transforms that were applied, in order */
  appliedTransforms: string[];
}
