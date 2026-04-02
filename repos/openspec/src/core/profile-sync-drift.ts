import path from 'path';
import * as fs from 'fs';
import { AI_TOOLS, type CommandSurface } from './config.js';
import type { Delivery } from './global-config.js';
import { ALL_WORKFLOWS } from './profiles.js';
import { CommandAdapterRegistry } from './command-generation/index.js';
import { COMMAND_IDS, getConfiguredTools } from './shared/index.js';
import { resolveCommandSurface, supportsCommandsDelivery } from './shared/command-surface.js';
import { getSkillDirForWorkflow, resolveSkillsDir } from './templates/tool-profile-registry.js';

type WorkflowId = (typeof ALL_WORKFLOWS)[number];

/**
 * Maps workflow IDs to their skill directory names.
 * Delegates to manifest-derived ToolProfileRegistry.
 */
export function getWorkflowSkillDir(workflow: WorkflowId): string | undefined {
  return getSkillDirForWorkflow(workflow);
}

function toKnownWorkflows(workflows: readonly string[]): WorkflowId[] {
  return workflows.filter(
    (workflow): workflow is WorkflowId =>
      (ALL_WORKFLOWS as readonly string[]).includes(workflow)
  );
}

/**
 * Checks whether a tool has at least one generated OpenSpec command file.
 */
export function toolHasAnyConfiguredCommand(projectPath: string, toolId: string): boolean {
  const adapter = CommandAdapterRegistry.get(toolId);
  if (!adapter) return false;

  for (const commandId of COMMAND_IDS) {
    const cmdPath = adapter.getFilePath(commandId);
    const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);
    if (fs.existsSync(fullPath)) {
      return true;
    }
  }

  return false;
}

/**
 * Returns tools with at least one generated command file on disk.
 */
export function getCommandConfiguredTools(projectPath: string): string[] {
  return AI_TOOLS
    .filter((tool) => {
      if (!tool.skillsDir) return false;
      const toolDir = path.join(projectPath, tool.skillsDir);
      try {
        return fs.statSync(toolDir).isDirectory();
      } catch {
        return false;
      }
    })
    .map((tool) => tool.value)
    .filter((toolId) => toolHasAnyConfiguredCommand(projectPath, toolId));
}

/**
 * Returns tools that are configured via either skills or commands.
 */
export function getConfiguredToolsForProfileSync(projectPath: string): string[] {
  const skillConfigured = getConfiguredTools(projectPath);
  const commandConfigured = getCommandConfiguredTools(projectPath);
  return [...new Set([...skillConfigured, ...commandConfigured])];
}

/**
 * Computes per-tool effective skill/command generation booleans from
 * delivery mode + command surface capability.
 */
function toolEffectiveActions(delivery: Delivery, surface: CommandSurface): {
  shouldGenerateSkills: boolean;
  shouldGenerateCommands: boolean;
} {
  const shouldGenerateSkills =
    delivery === 'skills' || delivery === 'both' || (delivery === 'commands' && surface === 'skills-invocable');
  const shouldGenerateCommands =
    (delivery === 'commands' || delivery === 'both') && supportsCommandsDelivery(surface);
  return { shouldGenerateSkills, shouldGenerateCommands };
}

/**
 * Detects if a single tool has profile/delivery drift against the desired state.
 *
 * This function covers:
 * - required artifacts missing for selected workflows
 * - artifacts that should not exist for the selected delivery mode
 * - artifacts for workflows that were deselected from the current profile
 */
export function hasToolProfileOrDeliveryDrift(
  projectPath: string,
  toolId: string,
  desiredWorkflows: readonly string[],
  delivery: Delivery
): boolean {
  const tool = AI_TOOLS.find((t) => t.value === toolId);
  if (!tool?.skillsDir) return false;

  const knownDesiredWorkflows = toKnownWorkflows(desiredWorkflows);
  const desiredWorkflowSet = new Set<WorkflowId>(knownDesiredWorkflows);
  const skillsDir = path.join(projectPath, tool.skillsDir, 'skills');
  const adapter = CommandAdapterRegistry.get(toolId);

  // Resolve this tool's command surface and compute effective actions
  const surface = resolveCommandSurface(toolId, !!adapter);
  const { shouldGenerateSkills, shouldGenerateCommands } = toolEffectiveActions(delivery, surface);

  if (shouldGenerateSkills) {
    for (const workflow of knownDesiredWorkflows) {
      const dirName = getSkillDirForWorkflow(workflow);
      if (!dirName) continue;
      const skillFile = path.join(skillsDir, dirName, 'SKILL.md');
      if (!fs.existsSync(skillFile)) {
        return true;
      }
    }

    // Deselecting workflows in a profile should trigger sync.
    for (const workflow of ALL_WORKFLOWS) {
      if (desiredWorkflowSet.has(workflow)) continue;
      const dirName = getSkillDirForWorkflow(workflow);
      if (!dirName) continue;
      const skillDir = path.join(skillsDir, dirName);
      if (fs.existsSync(skillDir)) {
        return true;
      }
    }
  } else {
    // Skills should not exist for this tool under current delivery
    for (const workflow of ALL_WORKFLOWS) {
      const dirName = getSkillDirForWorkflow(workflow);
      if (!dirName) continue;
      const skillDir = path.join(skillsDir, dirName);
      if (fs.existsSync(skillDir)) {
        return true;
      }
    }
  }

  if (shouldGenerateCommands && adapter) {
    for (const workflow of knownDesiredWorkflows) {
      const cmdPath = adapter.getFilePath(workflow);
      const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);
      if (!fs.existsSync(fullPath)) {
        return true;
      }
    }

    // Deselecting workflows in a profile should trigger sync.
    for (const workflow of ALL_WORKFLOWS) {
      if (desiredWorkflowSet.has(workflow)) continue;
      const cmdPath = adapter.getFilePath(workflow);
      const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);
      if (fs.existsSync(fullPath)) {
        return true;
      }
    }
  } else if (!shouldGenerateCommands && adapter) {
    for (const workflow of ALL_WORKFLOWS) {
      const cmdPath = adapter.getFilePath(workflow);
      const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);
      if (fs.existsSync(fullPath)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Returns configured tools that currently need a profile/delivery sync.
 */
export function getToolsNeedingProfileSync(
  projectPath: string,
  desiredWorkflows: readonly string[],
  delivery: Delivery,
  configuredTools?: readonly string[]
): string[] {
  const tools = configuredTools ? [...new Set(configuredTools)] : getConfiguredToolsForProfileSync(projectPath);
  return tools.filter((toolId) =>
    hasToolProfileOrDeliveryDrift(projectPath, toolId, desiredWorkflows, delivery)
  );
}

function getInstalledWorkflowsForTool(
  projectPath: string,
  toolId: string,
  options: { includeSkills: boolean; includeCommands: boolean }
): WorkflowId[] {
  const tool = AI_TOOLS.find((t) => t.value === toolId);
  if (!tool?.skillsDir) return [];

  const installed = new Set<WorkflowId>();
  const skillsDir = path.join(projectPath, tool.skillsDir, 'skills');

  if (options.includeSkills) {
    for (const workflow of ALL_WORKFLOWS) {
      const dirName = getSkillDirForWorkflow(workflow);
      if (!dirName) continue;
      const skillFile = path.join(skillsDir, dirName, 'SKILL.md');
      if (fs.existsSync(skillFile)) {
        installed.add(workflow);
      }
    }
  }

  if (options.includeCommands) {
    const adapter = CommandAdapterRegistry.get(toolId);
    if (adapter) {
      for (const workflow of ALL_WORKFLOWS) {
        const cmdPath = adapter.getFilePath(workflow);
        const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);
        if (fs.existsSync(fullPath)) {
          installed.add(workflow);
        }
      }
    }
  }

  return [...installed];
}

/**
 * Detects whether the current project has any profile/delivery drift.
 */
export function hasProjectConfigDrift(
  projectPath: string,
  desiredWorkflows: readonly string[],
  delivery: Delivery
): boolean {
  const configuredTools = getConfiguredToolsForProfileSync(projectPath);
  if (getToolsNeedingProfileSync(projectPath, desiredWorkflows, delivery, configuredTools).length > 0) {
    return true;
  }

  const desiredSet = new Set(toKnownWorkflows(desiredWorkflows));

  for (const toolId of configuredTools) {
    // Resolve per-tool effective actions
    const adapter = CommandAdapterRegistry.get(toolId);
    const surface = resolveCommandSurface(toolId, !!adapter);
    const { shouldGenerateSkills, shouldGenerateCommands } = toolEffectiveActions(delivery, surface);
    const installed = getInstalledWorkflowsForTool(projectPath, toolId, {
      includeSkills: shouldGenerateSkills,
      includeCommands: shouldGenerateCommands,
    });
    if (installed.some((workflow) => !desiredSet.has(workflow))) {
      return true;
    }
  }

  return false;
}
