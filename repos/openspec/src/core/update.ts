/**
 * Update Command
 *
 * Refreshes OpenSpec skills and commands for configured tools.
 * Supports profile-aware updates, delivery changes, migration, and smart update detection.
 */

import path from 'path';
import chalk from 'chalk';
import ora from 'ora';
import * as fs from 'fs';
import { createRequire } from 'module';
import { FileSystemUtils } from '../utils/file-system.js';
import { AI_TOOLS, OPENSPEC_DIR_NAME } from './config.js';
import {
  generateCommands,
  CommandAdapterRegistry,
} from './command-generation/index.js';
import {
  renderSkills,
  renderCommands,
  writeArtifacts,
  type ArtifactToolDescriptor,
} from './templates/artifact-sync-engine.js';
import {
  getToolVersionStatus,
  getSkillTemplates,
  getCommandContents,
  generateSkillContentWithPipeline,
  getToolsWithSkillsDir,
  type ToolVersionStatus,
  resolveCommandSurface,
  resolveCommandSurfaces,
  supportsCommandsDelivery,
} from './shared/index.js';
import type { CommandSurface } from './config.js';
import {
  detectLegacyArtifacts,
  cleanupLegacyArtifacts,
  formatCleanupSummary,
  formatDetectionSummary,
  getToolsFromLegacyArtifacts,
  type LegacyDetectionResult,
} from './legacy-cleanup.js';
import { isInteractive } from '../utils/interactive.js';
import { getGlobalConfig, type Delivery } from './global-config.js';
import { getProfileWorkflows, ALL_WORKFLOWS } from './profiles.js';
import { getAvailableTools } from './available-tools.js';
import {
  getWorkflowSkillDir,
  getCommandConfiguredTools,
  getConfiguredToolsForProfileSync,
  getToolsNeedingProfileSync,
} from './profile-sync-drift.js';
import {
  scanInstalledWorkflows as scanInstalledWorkflowsShared,
  migrateIfNeeded as migrateIfNeededShared,
} from './migration.js';

const require = createRequire(import.meta.url);
const { version: OPENSPEC_VERSION } = require('../../package.json');

/**
 * Options for the update command.
 */
export interface UpdateCommandOptions {
  /** Force update even when tools are up to date */
  force?: boolean;
}

/**
 * Scans installed workflow artifacts (skills and managed commands) across all configured tools.
 * Returns the union of detected workflow IDs that match ALL_WORKFLOWS.
 *
 * Wrapper around the shared migration module's scanInstalledWorkflows that accepts tool IDs.
 */
export function scanInstalledWorkflows(projectPath: string, toolIds: string[]): string[] {
  const tools = toolIds
    .map((id) => AI_TOOLS.find((t) => t.value === id))
    .filter((t): t is NonNullable<typeof t> => t != null);
  return scanInstalledWorkflowsShared(projectPath, tools);
}

export class UpdateCommand {
  private readonly force: boolean;

  constructor(options: UpdateCommandOptions = {}) {
    this.force = options.force ?? false;
  }

  async execute(projectPath: string): Promise<void> {
    const resolvedProjectPath = path.resolve(projectPath);
    const openspecPath = path.join(resolvedProjectPath, OPENSPEC_DIR_NAME);

    // 1. Check openspec directory exists
    if (!await FileSystemUtils.directoryExists(openspecPath)) {
      throw new Error(`No OpenSpec directory found. Run 'openspec init' first.`);
    }

    // 2. Perform one-time migration if needed before any legacy upgrade generation.
    // Use detected tool directories to preserve existing opsx skills/commands.
    const detectedTools = getAvailableTools(resolvedProjectPath);
    migrateIfNeededShared(resolvedProjectPath, detectedTools);

    // 3. Read global config for profile/delivery
    const globalConfig = getGlobalConfig();
    const profile = globalConfig.profile ?? 'core';
    const delivery: Delivery = globalConfig.delivery ?? 'both';
    const profileWorkflows = getProfileWorkflows(profile, globalConfig.workflows);
    const desiredWorkflows = profileWorkflows.filter((workflow): workflow is (typeof ALL_WORKFLOWS)[number] =>
      (ALL_WORKFLOWS as readonly string[]).includes(workflow)
    );
    // 4. Detect and handle legacy artifacts + upgrade legacy tools using effective config
    const newlyConfiguredTools = await this.handleLegacyCleanup(
      resolvedProjectPath,
      desiredWorkflows,
      delivery
    );

    // 5. Find configured tools
    const configuredTools = getConfiguredToolsForProfileSync(resolvedProjectPath);

    if (configuredTools.length === 0 && newlyConfiguredTools.length === 0) {
      console.log(chalk.yellow('No configured tools found.'));
      console.log(chalk.dim('Run "openspec init" to set up tools.'));
      return;
    }

    // 6. Check version status for all configured tools
    const commandConfiguredTools = getCommandConfiguredTools(resolvedProjectPath);
    const commandConfiguredSet = new Set(commandConfiguredTools);
    const toolStatuses = configuredTools.map((toolId) => {
      const status = getToolVersionStatus(resolvedProjectPath, toolId, OPENSPEC_VERSION);
      if (!status.configured && commandConfiguredSet.has(toolId)) {
        return { ...status, configured: true };
      }
      return status;
    });
    const statusByTool = new Map(toolStatuses.map((status) => [status.toolId, status] as const));

    // 7. Smart update detection
    const toolsNeedingVersionUpdate = toolStatuses
      .filter((s) => s.needsUpdate)
      .map((s) => s.toolId);
    const toolsNeedingConfigSync = getToolsNeedingProfileSync(
      resolvedProjectPath,
      desiredWorkflows,
      delivery,
      configuredTools
    );
    const toolsToUpdateSet = new Set<string>([
      ...toolsNeedingVersionUpdate,
      ...toolsNeedingConfigSync,
    ]);
    const toolsUpToDate = toolStatuses.filter((s) => !toolsToUpdateSet.has(s.toolId));

    if (!this.force && toolsToUpdateSet.size === 0) {
      // All tools are up to date
      this.displayUpToDateMessage(toolStatuses);

      // Still check for new tool directories and extra workflows
      this.detectNewTools(resolvedProjectPath, configuredTools);
      this.displayExtraWorkflowsNote(resolvedProjectPath, configuredTools, desiredWorkflows);
      return;
    }

    // 8. Resolve per-tool command surfaces for configured tools
    const surfaceMap = resolveCommandSurfaces(
      configuredTools,
      (toolId) => CommandAdapterRegistry.has(toolId)
    );

    // 8b. Preflight: fail before partial updates when delivery=commands includes a tool with 'none' surface
    if (delivery === 'commands') {
      const unsupportedTools = configuredTools.filter(
        (toolId) => surfaceMap.get(toolId) === 'none'
      );
      if (unsupportedTools.length > 0) {
        const names = unsupportedTools.join(', ');
        throw new Error(
          `Incompatible tools for commands delivery: ${names}. ` +
          `These tools have no command surface (neither adapter nor skills-invocable). ` +
          `Change delivery to 'both' or 'skills', or remove these tools from configuration.`
        );
      }
    }

    // 9. Display update plan
    if (this.force) {
      console.log(`Force updating ${configuredTools.length} tool(s): ${configuredTools.join(', ')}`);
    } else {
      this.displayUpdatePlan([...toolsToUpdateSet], statusByTool, toolsUpToDate);
    }
    console.log();

    // 10. Prepare templates (will be filtered per-tool in the loop)
    const skillTemplates = getSkillTemplates(desiredWorkflows);
    const commandContents = getCommandContents(desiredWorkflows);

    // 11. Update tools (all if force, otherwise only those needing update)
    const toolsToUpdate = this.force ? configuredTools : [...toolsToUpdateSet];
    const updatedTools: string[] = [];
    const failedTools: Array<{ name: string; error: string }> = [];
    const skillsInvocableUpdated: string[] = [];
    let removedCommandCount = 0;
    let removedSkillCount = 0;
    let removedDeselectedCommandCount = 0;
    let removedDeselectedSkillCount = 0;

    for (const toolId of toolsToUpdate) {
      const tool = AI_TOOLS.find((t) => t.value === toolId);
      if (!tool?.skillsDir) continue;

      const spinner = ora(`Updating ${tool.name}...`).start();
      const surface = surfaceMap.get(toolId) ?? 'none';

      try {
        // Determine per-tool effective actions based on delivery + command surface
        const toolShouldGenerateSkills = this.toolShouldGenerateSkills(delivery, surface);
        const toolShouldGenerateCommands = this.toolShouldGenerateCommands(delivery, surface);

        const skillsDir = path.join(resolvedProjectPath, tool.skillsDir, 'skills');

        // Generate skill files if this tool's effective action includes skills
        if (toolShouldGenerateSkills) {
          const engineTool: ArtifactToolDescriptor = { toolId: tool.value, name: tool.name, skillsDir: tool.skillsDir };
          const renderedSkills = renderSkills(resolvedProjectPath, engineTool, skillTemplates, OPENSPEC_VERSION);
          await writeArtifacts(renderedSkills, []);

          removedDeselectedSkillCount += await this.removeUnselectedSkillDirs(skillsDir, desiredWorkflows);
        }

        // Delete skill directories if this tool's effective action does NOT include skills
        if (!toolShouldGenerateSkills) {
          removedSkillCount += await this.removeSkillDirs(skillsDir);
        }

        // Generate commands if this tool's effective action includes commands
        if (toolShouldGenerateCommands) {
          const adapter = CommandAdapterRegistry.get(tool.value);
          if (adapter) {
            const engineTool: ArtifactToolDescriptor = { toolId: tool.value, name: tool.name, skillsDir: tool.skillsDir };
            const renderedCmds = renderCommands(resolvedProjectPath, engineTool, commandContents);
            await writeArtifacts([], renderedCmds);

            removedDeselectedCommandCount += await this.removeUnselectedCommandFiles(
              resolvedProjectPath,
              toolId,
              desiredWorkflows
            );
          }
          // skills-invocable tools don't use adapters; this is expected
          if (surface === 'skills-invocable') {
            skillsInvocableUpdated.push(tool.name);
          }
        }

        // Delete command files if this tool's effective action does NOT include commands
        if (!toolShouldGenerateCommands) {
          removedCommandCount += await this.removeCommandFiles(resolvedProjectPath, toolId);
        }

        spinner.succeed(`Updated ${tool.name}`);
        updatedTools.push(tool.name);
      } catch (error) {
        spinner.fail(`Failed to update ${tool.name}`);
        failedTools.push({
          name: tool.name,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }

    // 12. Summary
    console.log();
    if (updatedTools.length > 0) {
      console.log(chalk.green(`✓ Updated: ${updatedTools.join(', ')} (v${OPENSPEC_VERSION})`));
    }
    if (failedTools.length > 0) {
      console.log(chalk.red(`✗ Failed: ${failedTools.map(f => `${f.name} (${f.error})`).join(', ')}`));
    }
    // Report skills-invocable tools using skills as command surface (step 3.6)
    if (skillsInvocableUpdated.length > 0) {
      console.log(chalk.dim(`Skills used as command surface for: ${skillsInvocableUpdated.join(', ')}`));
    }
    if (removedCommandCount > 0) {
      console.log(chalk.dim(`Removed: ${removedCommandCount} command files (delivery: skills)`));
    }
    if (removedSkillCount > 0) {
      console.log(chalk.dim(`Removed: ${removedSkillCount} skill directories (delivery: commands)`));
    }
    if (removedDeselectedCommandCount > 0) {
      console.log(chalk.dim(`Removed: ${removedDeselectedCommandCount} command files (deselected workflows)`));
    }
    if (removedDeselectedSkillCount > 0) {
      console.log(chalk.dim(`Removed: ${removedDeselectedSkillCount} skill directories (deselected workflows)`));
    }

    // 12. Show onboarding message for newly configured tools from legacy upgrade
    if (newlyConfiguredTools.length > 0) {
      console.log();
      console.log(chalk.bold('Getting started:'));
      console.log('  /opsx:new       Start a new change');
      console.log('  /opsx:continue  Create the next artifact');
      console.log('  /opsx:apply     Implement tasks');
      console.log();
      console.log(`Learn more: ${chalk.cyan('https://github.com/Fission-AI/OpenSpec')}`);
    }

    const configuredAndNewTools = [...new Set([...configuredTools, ...newlyConfiguredTools])];

    // 13. Detect new tool directories not currently configured
    this.detectNewTools(resolvedProjectPath, configuredAndNewTools);

    // 14. Display note about extra workflows not in profile
    this.displayExtraWorkflowsNote(resolvedProjectPath, configuredAndNewTools, desiredWorkflows);

    // 15. List affected tools
    if (updatedTools.length > 0) {
      const toolDisplayNames = updatedTools;
      console.log(chalk.dim(`Tools: ${toolDisplayNames.join(', ')}`));
    }

    console.log();
    console.log(chalk.dim('Restart your IDE for changes to take effect.'));
  }

  /**
   * Whether a tool should generate (keep/create) skills given the delivery mode
   * and its resolved command surface.
   */
  private toolShouldGenerateSkills(delivery: Delivery, surface: CommandSurface): boolean {
    // delivery=skills or delivery=both: always generate skills
    if (delivery === 'skills' || delivery === 'both') return true;
    // delivery=commands: only generate skills for skills-invocable tools
    return surface === 'skills-invocable';
  }

  /**
   * Whether a tool should generate commands given the delivery mode
   * and its resolved command surface.
   */
  private toolShouldGenerateCommands(delivery: Delivery, surface: CommandSurface): boolean {
    // delivery=commands or delivery=both: generate commands for supported surfaces
    if (delivery === 'commands' || delivery === 'both') {
      return supportsCommandsDelivery(surface);
    }
    // delivery=skills: no commands
    return false;
  }

  /**
   * Display message when all tools are up to date.
   */
  private displayUpToDateMessage(toolStatuses: ToolVersionStatus[]): void {
    const toolNames = toolStatuses.map((s) => s.toolId);
    console.log(chalk.green(`✓ All ${toolStatuses.length} tool(s) up to date (v${OPENSPEC_VERSION})`));
    console.log(chalk.dim(`  Tools: ${toolNames.join(', ')}`));
    console.log();
    console.log(chalk.dim('Use --force to refresh files anyway.'));
  }

  /**
   * Display the update plan showing which tools need updating.
   */
  private displayUpdatePlan(
    toolsToUpdate: string[],
    statusByTool: Map<string, ToolVersionStatus>,
    upToDate: ToolVersionStatus[]
  ): void {
    const updates = toolsToUpdate.map((toolId) => {
      const status = statusByTool.get(toolId);
      if (status?.needsUpdate) {
        const fromVersion = status.generatedByVersion ?? 'unknown';
        return `${status.toolId} (${fromVersion} → ${OPENSPEC_VERSION})`;
      }
      return `${toolId} (config sync)`;
    });

    console.log(`Updating ${toolsToUpdate.length} tool(s): ${updates.join(', ')}`);

    if (upToDate.length > 0) {
      const upToDateNames = upToDate.map((s) => s.toolId);
      console.log(chalk.dim(`Already up to date: ${upToDateNames.join(', ')}`));
    }
  }

  /**
   * Detects new tool directories that aren't currently configured and displays a hint.
   */
  private detectNewTools(projectPath: string, configuredTools: string[]): void {
    const availableTools = getAvailableTools(projectPath);
    const configuredSet = new Set(configuredTools);

    const newTools = availableTools.filter((t) => !configuredSet.has(t.value));

    if (newTools.length > 0) {
      const newToolNames = newTools.map((tool) => tool.name);
      const isSingleTool = newToolNames.length === 1;
      const toolNoun = isSingleTool ? 'tool' : 'tools';
      const pronoun = isSingleTool ? 'it' : 'them';
      console.log();
      console.log(
        chalk.yellow(
          `Detected new ${toolNoun}: ${newToolNames.join(', ')}. Run 'openspec init' to add ${pronoun}.`
        )
      );
    }
  }

  /**
   * Displays a note about extra workflows installed that aren't in the current profile.
   */
  private displayExtraWorkflowsNote(
    projectPath: string,
    configuredTools: string[],
    profileWorkflows: readonly string[]
  ): void {
    const installedWorkflows = scanInstalledWorkflows(projectPath, configuredTools);
    const profileSet = new Set(profileWorkflows);
    const extraWorkflows = installedWorkflows.filter((w) => !profileSet.has(w));

    if (extraWorkflows.length > 0) {
      console.log(chalk.dim(`Note: ${extraWorkflows.length} extra workflows not in profile (use \`openspec config profile\` to manage)`));
    }
  }

  /**
   * Removes skill directories for workflows when delivery changed to commands-only.
   * Returns the number of directories removed.
   */
  private async removeSkillDirs(skillsDir: string): Promise<number> {
    let removed = 0;

    for (const workflow of ALL_WORKFLOWS) {
      const dirName = getWorkflowSkillDir(workflow);
      if (!dirName) continue;

      const skillDir = path.join(skillsDir, dirName);
      try {
        if (fs.existsSync(skillDir)) {
          await fs.promises.rm(skillDir, { recursive: true, force: true });
          removed++;
        }
      } catch {
        // Ignore errors
      }
    }

    return removed;
  }

  /**
   * Removes skill directories for workflows that are no longer selected in the active profile.
   * Returns the number of directories removed.
   */
  private async removeUnselectedSkillDirs(
    skillsDir: string,
    desiredWorkflows: readonly (typeof ALL_WORKFLOWS)[number][]
  ): Promise<number> {
    const desiredSet = new Set(desiredWorkflows);
    let removed = 0;

    for (const workflow of ALL_WORKFLOWS) {
      if (desiredSet.has(workflow)) continue;
      const dirName = getWorkflowSkillDir(workflow);
      if (!dirName) continue;

      const skillDir = path.join(skillsDir, dirName);
      try {
        if (fs.existsSync(skillDir)) {
          await fs.promises.rm(skillDir, { recursive: true, force: true });
          removed++;
        }
      } catch {
        // Ignore errors
      }
    }

    return removed;
  }

  /**
   * Removes command files for workflows when delivery changed to skills-only.
   * Returns the number of files removed.
   */
  private async removeCommandFiles(
    projectPath: string,
    toolId: string,
  ): Promise<number> {
    let removed = 0;

    const adapter = CommandAdapterRegistry.get(toolId);
    if (!adapter) return 0;

    for (const workflow of ALL_WORKFLOWS) {
      const cmdPath = adapter.getFilePath(workflow);
      const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);

      try {
        if (fs.existsSync(fullPath)) {
          await fs.promises.unlink(fullPath);
          removed++;
        }
      } catch {
        // Ignore errors
      }
    }

    return removed;
  }

  /**
   * Removes command files for workflows that are no longer selected in the active profile.
   * Returns the number of files removed.
   */
  private async removeUnselectedCommandFiles(
    projectPath: string,
    toolId: string,
    desiredWorkflows: readonly (typeof ALL_WORKFLOWS)[number][]
  ): Promise<number> {
    let removed = 0;

    const adapter = CommandAdapterRegistry.get(toolId);
    if (!adapter) return 0;

    const desiredSet = new Set(desiredWorkflows);

    for (const workflow of ALL_WORKFLOWS) {
      if (desiredSet.has(workflow)) continue;
      const cmdPath = adapter.getFilePath(workflow);
      const fullPath = path.isAbsolute(cmdPath) ? cmdPath : path.join(projectPath, cmdPath);

      try {
        if (fs.existsSync(fullPath)) {
          await fs.promises.unlink(fullPath);
          removed++;
        }
      } catch {
        // Ignore errors
      }
    }

    return removed;
  }

  /**
   * Detect and handle legacy OpenSpec artifacts.
   * Unlike init, update warns but continues if legacy files found in non-interactive mode.
   * Returns array of tool IDs that were newly configured during legacy upgrade.
   */
  private async handleLegacyCleanup(
    projectPath: string,
    desiredWorkflows: readonly (typeof ALL_WORKFLOWS)[number][],
    delivery: Delivery
  ): Promise<string[]> {
    // Detect legacy artifacts
    const detection = await detectLegacyArtifacts(projectPath);

    if (!detection.hasLegacyArtifacts) {
      return []; // No legacy artifacts found
    }

    // Show what was detected
    console.log();
    console.log(formatDetectionSummary(detection));
    console.log();

    const canPrompt = isInteractive();

    if (this.force) {
      // --force flag: proceed with cleanup automatically
      await this.performLegacyCleanup(projectPath, detection);
      // Then upgrade legacy tools to new skills
      return this.upgradeLegacyTools(projectPath, detection, canPrompt, desiredWorkflows, delivery);
    }

    if (!canPrompt) {
      // Non-interactive mode without --force: warn and continue
      // (Unlike init, update doesn't abort - user may just want to update skills)
      console.log(chalk.yellow('⚠ Run with --force to auto-cleanup legacy files, or run interactively.'));
      console.log();
      return [];
    }

    // Interactive mode: prompt for confirmation
    const { confirm } = await import('@inquirer/prompts');
    const shouldCleanup = await confirm({
      message: 'Upgrade and clean up legacy files?',
      default: true,
    });

    if (shouldCleanup) {
      await this.performLegacyCleanup(projectPath, detection);
      // Then upgrade legacy tools to new skills
      return this.upgradeLegacyTools(projectPath, detection, canPrompt, desiredWorkflows, delivery);
    } else {
      console.log(chalk.dim('Skipping legacy cleanup. Continuing with skill update...'));
      console.log();
      return [];
    }
  }

  /**
   * Perform cleanup of legacy artifacts.
   */
  private async performLegacyCleanup(projectPath: string, detection: LegacyDetectionResult): Promise<void> {
    const spinner = ora('Cleaning up legacy files...').start();

    const result = await cleanupLegacyArtifacts(projectPath, detection);

    spinner.succeed('Legacy files cleaned up');

    const summary = formatCleanupSummary(result);
    if (summary) {
      console.log();
      console.log(summary);
    }

    console.log();
  }

  /**
   * Upgrade legacy tools to new skills system.
   * Returns array of tool IDs that were newly configured.
   */
  private async upgradeLegacyTools(
    projectPath: string,
    detection: LegacyDetectionResult,
    canPrompt: boolean,
    desiredWorkflows: readonly (typeof ALL_WORKFLOWS)[number][],
    delivery: Delivery
  ): Promise<string[]> {
    // Get tools that had legacy artifacts
    const legacyTools = getToolsFromLegacyArtifacts(detection);

    if (legacyTools.length === 0) {
      return [];
    }

    // Get currently configured tools
    const configuredTools = getConfiguredToolsForProfileSync(projectPath);
    const configuredSet = new Set(configuredTools);

    // Filter to tools that aren't already configured
    const unconfiguredLegacyTools = legacyTools.filter((t) => !configuredSet.has(t));

    if (unconfiguredLegacyTools.length === 0) {
      return [];
    }

    // Get valid tools (those with skillsDir)
    const validToolIds = new Set(getToolsWithSkillsDir());
    const validUnconfiguredTools = unconfiguredLegacyTools.filter((t) => validToolIds.has(t));

    if (validUnconfiguredTools.length === 0) {
      return [];
    }

    // Show what tools were detected from legacy artifacts
    console.log(chalk.bold('Tools detected from legacy artifacts:'));
    for (const toolId of validUnconfiguredTools) {
      const tool = AI_TOOLS.find((t) => t.value === toolId);
      console.log(`  • ${tool?.name || toolId}`);
    }
    console.log();

    let selectedTools: string[];

    if (this.force || !canPrompt) {
      // Non-interactive with --force: auto-select detected tools
      selectedTools = validUnconfiguredTools;
      console.log(`Setting up skills for: ${selectedTools.join(', ')}`);
    } else {
      // Interactive mode: prompt for tool selection with detected tools pre-selected
      const { searchableMultiSelect } = await import('../prompts/searchable-multi-select.js');

      const sortedChoices = validUnconfiguredTools.map((toolId) => {
        const tool = AI_TOOLS.find((t) => t.value === toolId);
        return {
          name: tool?.name || toolId,
          value: toolId,
          configured: false,
          preSelected: true, // Pre-select all detected legacy tools
        };
      });

      selectedTools = await searchableMultiSelect({
        message: 'Select tools to set up with the new skill system:',
        pageSize: 15,
        choices: sortedChoices,
        validate: (_selected: string[]) => true, // Allow empty selection (user can skip)
      });

      if (selectedTools.length === 0) {
        console.log(chalk.dim('Skipping tool setup.'));
        console.log();
        return [];
      }
    }

    // Create skills/commands for selected tools using effective profile+delivery.
    const newlyConfigured: string[] = [];
    const skillTemplates = getSkillTemplates(desiredWorkflows);
    const commandContents = getCommandContents(desiredWorkflows);

    // Resolve per-tool command surfaces for legacy tools
    const legacySurfaceMap = resolveCommandSurfaces(
      selectedTools,
      (toolId) => CommandAdapterRegistry.has(toolId)
    );

    for (const toolId of selectedTools) {
      const tool = AI_TOOLS.find((t) => t.value === toolId);
      if (!tool?.skillsDir) continue;

      const spinner = ora(`Setting up ${tool.name}...`).start();
      const surface = legacySurfaceMap.get(toolId) ?? 'none';

      try {
        const skillsDir = path.join(projectPath, tool.skillsDir, 'skills');
        const toolShouldGenerateSkills = this.toolShouldGenerateSkills(delivery, surface);
        const toolShouldGenerateCommands = this.toolShouldGenerateCommands(delivery, surface);

        // Create skill files when this tool's effective action includes skills
        if (toolShouldGenerateSkills) {
          for (const { template, dirName, workflowId } of skillTemplates) {
            const skillDir = path.join(skillsDir, dirName);
            const skillFile = path.join(skillDir, 'SKILL.md');

            const skillContent = generateSkillContentWithPipeline(template, OPENSPEC_VERSION, {
              toolId: tool.value,
              workflowId,
            });
            await FileSystemUtils.writeFile(skillFile, skillContent);
          }
        }

        // Create commands when this tool's effective action includes commands
        if (toolShouldGenerateCommands) {
          const adapter = CommandAdapterRegistry.get(tool.value);
          if (adapter) {
            const generatedCommands = generateCommands(commandContents, adapter);

            for (const cmd of generatedCommands) {
              const commandFile = path.isAbsolute(cmd.path) ? cmd.path : path.join(projectPath, cmd.path);
              await FileSystemUtils.writeFile(commandFile, cmd.fileContent);
            }
          }
        }

        spinner.succeed(`Setup complete for ${tool.name}`);
        newlyConfigured.push(toolId);
      } catch (error) {
        spinner.fail(`Failed to set up ${tool.name}`);
        console.log(chalk.red(`  ${error instanceof Error ? error.message : String(error)}`));
      }
    }

    if (newlyConfigured.length > 0) {
      console.log();
    }

    return newlyConfigured;
  }
}
