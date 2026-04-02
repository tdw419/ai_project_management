/**
 * Artifact Sync Engine
 *
 * Shared engine for planning, rendering, and writing skill and command artifacts.
 * Consolidates the duplicated generation loops that were previously inlined in
 * init, update, and legacy-upgrade flows.
 *
 * The engine:
 * 1. Plans which artifacts to generate per tool (based on delivery + command surface)
 * 2. Renders skill content through the transform pipeline
 * 3. Renders command content through adapters
 * 4. Writes all rendered artifacts to disk
 *
 * All three consumers (init, update, legacy-upgrade) now delegate to this engine
 * instead of maintaining their own generation loops.
 */

import path from 'path';
import type { Delivery } from '../global-config.js';
import type { CommandSurface } from '../config.js';
import {
  generateCommands,
  CommandAdapterRegistry,
} from '../command-generation/index.js';
import {
  getSkillTemplates,
  getCommandContents,
  generateSkillContentWithPipeline,
  type SkillTemplateEntry,
} from '../shared/skill-generation.js';
import type { CommandContent } from '../command-generation/types.js';
import { FileSystemUtils } from '../../utils/file-system.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Describes a tool for artifact generation purposes.
 * This is the minimal contract the engine needs to generate artifacts.
 */
export interface ArtifactToolDescriptor {
  /** Tool identifier (e.g., 'claude', 'cursor') */
  toolId: string;
  /** Human-readable display name */
  name: string;
  /** Skills base directory relative to project root (e.g., '.claude') */
  skillsDir: string;
}

/**
 * Per-tool generation plan produced by the planning phase.
 */
export interface ArtifactPlan {
  tool: ArtifactToolDescriptor;
  shouldGenerateSkills: boolean;
  shouldGenerateCommands: boolean;
  commandSurface: CommandSurface;
}

/**
 * Result of syncing artifacts for a single tool.
 */
export interface ArtifactSyncResult {
  tool: ArtifactToolDescriptor;
  success: boolean;
  error?: Error;
  skillsWritten: number;
  commandsWritten: number;
}

/**
 * Aggregate result of syncing artifacts for multiple tools.
 */
export interface ArtifactSyncReport {
  results: ArtifactSyncResult[];
  totalSkillsWritten: number;
  totalCommandsWritten: number;
  failed: Array<{ name: string; error: Error }>;
  skillsInvocableTools: ArtifactToolDescriptor[];
}

/**
 * Options for the sync engine.
 */
export interface ArtifactSyncOptions {
  /** Absolute project path */
  projectPath: string;
  /** Tools to generate artifacts for */
  tools: ArtifactToolDescriptor[];
  /** Profile workflows filter (restricts which workflows are generated) */
  workflows: readonly string[];
  /** Delivery mode */
  delivery: Delivery;
  /** OpenSpec version for embedding in generated files */
  openspecVersion: string;
  /** Pre-resolved command surfaces per tool */
  surfaceMap: ReadonlyMap<string, CommandSurface>;
}

// ---------------------------------------------------------------------------
// Planning
// ---------------------------------------------------------------------------

/**
 * Determines whether a tool should generate skills based on delivery + surface.
 */
export function shouldGenerateSkills(delivery: Delivery, surface: CommandSurface): boolean {
  if (delivery === 'skills' || delivery === 'both') return true;
  return surface === 'skills-invocable';
}

/**
 * Determines whether a tool should generate commands based on delivery + surface.
 */
export function shouldGenerateCommands(delivery: Delivery, surface: CommandSurface): boolean {
  if (delivery === 'commands' || delivery === 'both') {
    return surface !== 'none';
  }
  return false;
}

/**
 * Builds a per-tool generation plan based on delivery mode and command surfaces.
 */
export function planArtifacts(
  tools: ArtifactToolDescriptor[],
  delivery: Delivery,
  surfaceMap: ReadonlyMap<string, CommandSurface>,
): ArtifactPlan[] {
  return tools.map((tool) => {
    const surface = surfaceMap.get(tool.toolId) ?? 'none';
    return {
      tool,
      shouldGenerateSkills: shouldGenerateSkills(delivery, surface),
      shouldGenerateCommands: shouldGenerateCommands(delivery, surface),
      commandSurface: surface,
    };
  });
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/**
 * A rendered skill artifact ready to write to disk.
 */
export interface RenderedSkill {
  /** Absolute file path */
  filePath: string;
  /** Rendered content */
  content: string;
}

/**
 * A rendered command artifact ready to write to disk.
 */
export interface RenderedCommand {
  /** Absolute file path */
  filePath: string;
  /** Rendered content */
  content: string;
}

/**
 * Renders all skill artifacts for a tool based on the plan.
 */
export function renderSkills(
  projectPath: string,
  tool: ArtifactToolDescriptor,
  skillTemplates: SkillTemplateEntry[],
  openspecVersion: string,
): RenderedSkill[] {
  const rendered: RenderedSkill[] = [];
  const skillsDir = path.join(projectPath, tool.skillsDir, 'skills');

  for (const { template, dirName, workflowId } of skillTemplates) {
    const skillDir = path.join(skillsDir, dirName);
    const skillFile = path.join(skillDir, 'SKILL.md');

    const content = generateSkillContentWithPipeline(template, openspecVersion, {
      toolId: tool.toolId,
      workflowId,
    });

    rendered.push({ filePath: skillFile, content });
  }

  return rendered;
}

/**
 * Renders all command artifacts for a tool based on the plan.
 */
export function renderCommands(
  projectPath: string,
  tool: ArtifactToolDescriptor,
  commandContents: CommandContent[],
): RenderedCommand[] {
  const adapter = CommandAdapterRegistry.get(tool.toolId);
  if (!adapter) return [];

  const generatedCommands = generateCommands(commandContents, adapter);
  return generatedCommands.map((cmd) => ({
    filePath: path.isAbsolute(cmd.path) ? cmd.path : path.join(projectPath, cmd.path),
    content: cmd.fileContent,
  }));
}

// ---------------------------------------------------------------------------
// Writing
// ---------------------------------------------------------------------------

/**
 * Writes rendered artifacts to disk.
 */
export async function writeArtifacts(
  skills: RenderedSkill[],
  commands: RenderedCommand[],
): Promise<{ skillsWritten: number; commandsWritten: number }> {
  for (const skill of skills) {
    await FileSystemUtils.writeFile(skill.filePath, skill.content);
  }
  for (const cmd of commands) {
    await FileSystemUtils.writeFile(cmd.filePath, cmd.content);
  }
  return {
    skillsWritten: skills.length,
    commandsWritten: commands.length,
  };
}

// ---------------------------------------------------------------------------
// Engine (full sync)
// ---------------------------------------------------------------------------

/**
 * Runs the full artifact sync pipeline for multiple tools.
 *
 * This is the main entry point for init, update, and legacy-upgrade flows.
 * It plans, renders, and writes artifacts for all specified tools.
 */
export async function syncArtifacts(options: ArtifactSyncOptions): Promise<ArtifactSyncReport> {
  const { projectPath, workflows, openspecVersion, delivery, surfaceMap } = options;

  // Get templates filtered by profile workflows
  const skillTemplates = getSkillTemplates(workflows);
  const commandContents = getCommandContents(workflows);

  // Build per-tool plans
  const plans = planArtifacts(options.tools, delivery, surfaceMap);

  const results: ArtifactSyncResult[] = [];
  const failed: Array<{ name: string; error: Error }> = [];
  const skillsInvocableTools: ArtifactToolDescriptor[] = [];
  let totalSkillsWritten = 0;
  let totalCommandsWritten = 0;

  for (const plan of plans) {
    try {
      let skillsWritten = 0;
      let commandsWritten = 0;

      // Render and write skills
      if (plan.shouldGenerateSkills) {
        const rendered = renderSkills(projectPath, plan.tool, skillTemplates, openspecVersion);
        const written = await writeArtifacts(rendered, []);
        skillsWritten = written.skillsWritten;
      }

      // Render and write commands
      if (plan.shouldGenerateCommands) {
        if (CommandAdapterRegistry.has(plan.tool.toolId)) {
          const rendered = renderCommands(projectPath, plan.tool, commandContents);
          const written = await writeArtifacts([], rendered);
          commandsWritten = written.commandsWritten;
        } else if (plan.commandSurface === 'skills-invocable') {
          skillsInvocableTools.push(plan.tool);
        }
      }

      totalSkillsWritten += skillsWritten;
      totalCommandsWritten += commandsWritten;

      results.push({
        tool: plan.tool,
        success: true,
        skillsWritten,
        commandsWritten,
      });
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      results.push({
        tool: plan.tool,
        success: false,
        error: err,
        skillsWritten: 0,
        commandsWritten: 0,
      });
      failed.push({ name: plan.tool.name, error: err });
    }
  }

  return {
    results,
    totalSkillsWritten,
    totalCommandsWritten,
    failed,
    skillsInvocableTools,
  };
}
