/**
 * Workflow Manifest Types
 *
 * Canonical type definitions for the workflow manifest registry.
 * These types serve as the single source of truth for workflow IDs,
 * skill metadata, and optional command descriptors.
 */

import type { SkillTemplate, CommandTemplate } from './types.js';

/**
 * Unique identifier for a workflow.
 * Must match the workflowId used in skill-generation and tool-detection.
 */
export type WorkflowId = string;

/**
 * Descriptor for a single workflow entry in the manifest.
 *
 * Each workflow can produce both a skill template (for tools with skillsDir)
 * and a command template (for tools with adapter-based command surfaces).
 *
 * Workflows that only have a skill template (e.g., feedback) set
 * hasCommand to false.
 *
 * Set `deployable: false` for workflows that are NOT deployed to tools
 * during init/update (e.g., feedback is a standalone-only workflow).
 */
export interface WorkflowManifestEntry {
  /** Unique workflow identifier (e.g., 'explore', 'new', 'apply') */
  workflowId: WorkflowId;

  /**
   * Whether this workflow is deployed to tools during init/update.
   * Non-deployable workflows are still registered as templates but
   * excluded from SKILL_NAMES, getSkillTemplates(), etc.
   * Default: true
   */
  deployable?: boolean;

  /** Skill-related metadata */
  skill: {
    /** Directory name used for the skill (e.g., 'openspec-explore') */
    dirName: string;
    /** Factory function that returns the skill template */
    getTemplate: () => SkillTemplate;
  };

  /** Command-related metadata. Omitted when workflow has no command surface. */
  command?: {
    /** Factory function that returns the command template */
    getTemplate: () => CommandTemplate;
  };
}

/**
 * The canonical workflow manifest.
 *
 * An ordered array of WorkflowManifestEntry objects that serves as the
 * single source of truth for all workflow definitions. Every consumer
 * (skill-generation, tool-detection, etc.) should derive its data
 * from this registry.
 */
export type WorkflowManifest = readonly WorkflowManifestEntry[];
