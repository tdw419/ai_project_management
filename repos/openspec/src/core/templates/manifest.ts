/**
 * Workflow Manifest Registry
 *
 * The canonical single source of truth for all workflow definitions.
 * Every consumer of workflow/skill/command data should derive from this registry.
 *
 * To add a new workflow:
 * 1. Create the workflow module in src/core/templates/workflows/<name>.ts
 * 2. Add an entry to WORKFLOW_MANIFEST below
 * 3. Re-export from skill-templates.ts if needed for backward compatibility
 */

export type { WorkflowManifestEntry, WorkflowManifest } from './manifest-types.js';
import type { WorkflowManifest } from './manifest-types.js';

import { getExploreSkillTemplate, getOpsxExploreCommandTemplate } from './workflows/explore.js';
import { getNewChangeSkillTemplate, getOpsxNewCommandTemplate } from './workflows/new-change.js';
import { getContinueChangeSkillTemplate, getOpsxContinueCommandTemplate } from './workflows/continue-change.js';
import { getApplyChangeSkillTemplate, getOpsxApplyCommandTemplate } from './workflows/apply-change.js';
import { getFfChangeSkillTemplate, getOpsxFfCommandTemplate } from './workflows/ff-change.js';
import { getSyncSpecsSkillTemplate, getOpsxSyncCommandTemplate } from './workflows/sync-specs.js';
import { getArchiveChangeSkillTemplate, getOpsxArchiveCommandTemplate } from './workflows/archive-change.js';
import { getBulkArchiveChangeSkillTemplate, getOpsxBulkArchiveCommandTemplate } from './workflows/bulk-archive-change.js';
import { getVerifyChangeSkillTemplate, getOpsxVerifyCommandTemplate } from './workflows/verify-change.js';
import { getOnboardSkillTemplate, getOpsxOnboardCommandTemplate } from './workflows/onboard.js';
import { getOpsxProposeSkillTemplate, getOpsxProposeCommandTemplate } from './workflows/propose.js';
import { getFeedbackSkillTemplate } from './workflows/feedback.js';

/**
 * The canonical workflow manifest.
 *
 * Order matters: consumers may rely on insertion order for deterministic output.
 */
export const WORKFLOW_MANIFEST: WorkflowManifest = [
  {
    workflowId: 'explore',
    skill: {
      dirName: 'openspec-explore',
      getTemplate: getExploreSkillTemplate,
    },
    command: {
      getTemplate: getOpsxExploreCommandTemplate,
    },
  },
  {
    workflowId: 'new',
    skill: {
      dirName: 'openspec-new-change',
      getTemplate: getNewChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxNewCommandTemplate,
    },
  },
  {
    workflowId: 'continue',
    skill: {
      dirName: 'openspec-continue-change',
      getTemplate: getContinueChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxContinueCommandTemplate,
    },
  },
  {
    workflowId: 'apply',
    skill: {
      dirName: 'openspec-apply-change',
      getTemplate: getApplyChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxApplyCommandTemplate,
    },
  },
  {
    workflowId: 'ff',
    skill: {
      dirName: 'openspec-ff-change',
      getTemplate: getFfChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxFfCommandTemplate,
    },
  },
  {
    workflowId: 'sync',
    skill: {
      dirName: 'openspec-sync-specs',
      getTemplate: getSyncSpecsSkillTemplate,
    },
    command: {
      getTemplate: getOpsxSyncCommandTemplate,
    },
  },
  {
    workflowId: 'archive',
    skill: {
      dirName: 'openspec-archive-change',
      getTemplate: getArchiveChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxArchiveCommandTemplate,
    },
  },
  {
    workflowId: 'bulk-archive',
    skill: {
      dirName: 'openspec-bulk-archive-change',
      getTemplate: getBulkArchiveChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxBulkArchiveCommandTemplate,
    },
  },
  {
    workflowId: 'verify',
    skill: {
      dirName: 'openspec-verify-change',
      getTemplate: getVerifyChangeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxVerifyCommandTemplate,
    },
  },
  {
    workflowId: 'onboard',
    skill: {
      dirName: 'openspec-onboard',
      getTemplate: getOnboardSkillTemplate,
    },
    command: {
      getTemplate: getOpsxOnboardCommandTemplate,
    },
  },
  {
    workflowId: 'propose',
    skill: {
      dirName: 'openspec-propose',
      getTemplate: getOpsxProposeSkillTemplate,
    },
    command: {
      getTemplate: getOpsxProposeCommandTemplate,
    },
  },
  {
    workflowId: 'feedback',
    deployable: false,
    skill: {
      dirName: 'openspec-feedback',
      getTemplate: getFeedbackSkillTemplate,
    },
    // feedback has no command surface
  },
] as const;

/**
 * Internal helper: returns only deployable entries.
 */
function getDeployableEntries() {
  return WORKFLOW_MANIFEST.filter((entry) => entry.deployable !== false);
}

/**
 * Returns manifest entries optionally filtered by workflow IDs.
 * Only returns deployable entries (suitable for init/update flows).
 */
export function getManifestEntries(workflowFilter?: readonly string[]) {
  const deployable = getDeployableEntries();
  if (!workflowFilter) return [...deployable];
  const filterSet = new Set(workflowFilter);
  return deployable.filter((entry) => filterSet.has(entry.workflowId));
}

/**
 * Returns all workflow IDs in manifest order (deployable only).
 */
export function getWorkflowIds(): string[] {
  return getDeployableEntries().map((entry) => entry.workflowId);
}

/**
 * Returns all skill directory names in manifest order (deployable only).
 */
export function getSkillDirNames(): string[] {
  return getDeployableEntries().map((entry) => entry.skill.dirName);
}

/**
 * Returns all command IDs in manifest order.
 * Only deployable entries with a command descriptor are included.
 */
export function getCommandIds(): string[] {
  return getDeployableEntries()
    .filter((entry) => entry.command != null)
    .map((entry) => entry.workflowId);
}
