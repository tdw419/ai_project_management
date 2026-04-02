/**
 * Agent Skill Templates
 *
 * Compatibility facade that re-exports split workflow template modules.
 * The canonical registry is now in manifest.ts.
 */

export type { SkillTemplate, CommandTemplate } from './types.js';

// Manifest types and registry
export type { WorkflowId, WorkflowManifestEntry, WorkflowManifest } from './manifest-types.js';
export {
  WORKFLOW_MANIFEST,
  getManifestEntries,
  getWorkflowIds,
  getSkillDirNames,
  getCommandIds,
} from './manifest.js';

// Individual workflow template re-exports (backward compatibility)
export { getExploreSkillTemplate, getOpsxExploreCommandTemplate } from './workflows/explore.js';
export { getNewChangeSkillTemplate, getOpsxNewCommandTemplate } from './workflows/new-change.js';
export { getContinueChangeSkillTemplate, getOpsxContinueCommandTemplate } from './workflows/continue-change.js';
export { getApplyChangeSkillTemplate, getOpsxApplyCommandTemplate } from './workflows/apply-change.js';
export { getFfChangeSkillTemplate, getOpsxFfCommandTemplate } from './workflows/ff-change.js';
export { getSyncSpecsSkillTemplate, getOpsxSyncCommandTemplate } from './workflows/sync-specs.js';
export { getArchiveChangeSkillTemplate, getOpsxArchiveCommandTemplate } from './workflows/archive-change.js';
export { getBulkArchiveChangeSkillTemplate, getOpsxBulkArchiveCommandTemplate } from './workflows/bulk-archive-change.js';
export { getVerifyChangeSkillTemplate, getOpsxVerifyCommandTemplate } from './workflows/verify-change.js';
export { getOnboardSkillTemplate, getOpsxOnboardCommandTemplate } from './workflows/onboard.js';
export { getOpsxProposeSkillTemplate, getOpsxProposeCommandTemplate } from './workflows/propose.js';
export { getFeedbackSkillTemplate } from './workflows/feedback.js';

// Tool profile layer (SEC-2)
export type {
  ToolProfile,
  SkillProfile,
  CommandProfile,
  WorkflowSkillDirMap,
  ToolProfileResolution,
} from './tool-profile-types.js';
export {
  getToolProfile,
  getAllToolProfiles,
  getToolsWithSkillsSupport,
  getToolsWithCommandAdapter,
  getAvailableToolsWithSkills,
  resolveSkillsDir,
  resolveSkillPath,
  getWorkflowSkillDirMap,
  getSkillDirForWorkflow,
  invalidateToolProfileCache,
} from './tool-profile-registry.js';

// Transform pipeline (SEC-3)
export type {
  Transform,
  TransformScope,
  TransformPhase,
  TransformContext,
  TransformResult,
} from './transform-types.js';
export {
  TransformPipeline,
  getTransformPipeline,
  resetTransformPipeline,
  openCodeHyphenTransform,
} from './transform-pipeline.js';
