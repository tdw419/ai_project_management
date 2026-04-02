/**
 * Shared Utilities
 *
 * Common code shared between init and update commands.
 */

export {
  SKILL_NAMES,
  type SkillName,
  COMMAND_IDS,
  type CommandId,
  type ToolSkillStatus,
  type ToolVersionStatus,
  getToolsWithSkillsDir,
  getToolSkillStatus,
  getToolStates,
  extractGeneratedByVersion,
  getToolVersionStatus,
  getConfiguredTools,
  getAllToolVersionStatus,
} from './tool-detection.js';

export {
  type SkillTemplateEntry,
  type CommandTemplateEntry,
  getSkillTemplates,
  getCommandTemplates,
  getCommandContents,
  generateSkillContent,
  generateSkillContentWithPipeline,
} from './skill-generation.js';

export {
  type Surface,
  type ScopeResolution,
  ScopeResolutionError,
  scopeResolutionErrorMessage,
  getSupportedScopes,
  resolveScope,
  resolveScopeForTool,
  resolveScopeForTools,
} from './scope-resolver.js';

export {
  resolveCommandSurface,
  resolveCommandSurfaces,
  supportsCommandsDelivery,
} from './command-surface.js';
