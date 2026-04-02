/**
 * Tool Detection Utilities
 *
 * Shared utilities for detecting tool configurations and version status.
 * SKILL_NAMES and COMMAND_IDS are now derived from the manifest registry.
 * Tool capability lookups use ToolProfileRegistry for unified access.
 */

import path from 'path';
import * as fs from 'fs';
import { AI_TOOLS } from '../config.js';
import { getSkillDirNames, getCommandIds } from '../templates/manifest.js';
import { getToolsWithSkillsSupport, resolveSkillsDir } from '../templates/tool-profile-registry.js';

/**
 * Names of skill directories created by openspec init.
 * Derived from the canonical workflow manifest.
 */
export const SKILL_NAMES = getSkillDirNames() as unknown as readonly [
  string,
  ...string[],
];

export type SkillName = (typeof SKILL_NAMES)[number];

/**
 * IDs of command templates created by openspec init.
 * Derived from the canonical workflow manifest.
 */
export const COMMAND_IDS = getCommandIds() as unknown as readonly [
  string,
  ...string[],
];

export type CommandId = (typeof COMMAND_IDS)[number];

/**
 * Status of skill configuration for a tool.
 */
export interface ToolSkillStatus {
  /** Whether the tool has any skills configured */
  configured: boolean;
  /** Whether all skills are configured */
  fullyConfigured: boolean;
  /** Number of skills currently configured */
  skillCount: number;
}

/**
 * Version information for a tool's skills.
 */
export interface ToolVersionStatus {
  /** The tool ID */
  toolId: string;
  /** The tool's display name */
  toolName: string;
  /** Whether the tool has any skills configured */
  configured: boolean;
  /** The generatedBy version found in the skill files, or null if not found */
  generatedByVersion: string | null;
  /** Whether the tool needs updating (version mismatch or missing) */
  needsUpdate: boolean;
}

/**
 * Gets the list of tools with skillsDir configured.
 * Uses ToolProfileRegistry for unified capability lookup.
 */
export function getToolsWithSkillsDir(): string[] {
  return getToolsWithSkillsSupport();
}

/**
 * Checks which skill files exist for a tool.
 * Uses ToolProfileRegistry for skillsDir resolution.
 */
export function getToolSkillStatus(projectRoot: string, toolId: string): ToolSkillStatus {
  const skillsDir = resolveSkillsDir(toolId);
  if (!skillsDir) {
    return { configured: false, fullyConfigured: false, skillCount: 0 };
  }

  const fullSkillsDir = path.join(projectRoot, skillsDir, 'skills');
  let skillCount = 0;

  for (const skillName of SKILL_NAMES) {
    const skillFile = path.join(fullSkillsDir, skillName, 'SKILL.md');
    if (fs.existsSync(skillFile)) {
      skillCount++;
    }
  }

  return {
    configured: skillCount > 0,
    fullyConfigured: skillCount === SKILL_NAMES.length,
    skillCount,
  };
}

/**
 * Gets the skill status for all tools with skillsDir configured.
 * Uses ToolProfileRegistry for capability lookup.
 */
export function getToolStates(projectRoot: string): Map<string, ToolSkillStatus> {
  const states = new Map<string, ToolSkillStatus>();
  const toolIds = getToolsWithSkillsSupport();

  for (const toolId of toolIds) {
    states.set(toolId, getToolSkillStatus(projectRoot, toolId));
  }

  return states;
}

/**
 * Extracts the generatedBy version from a skill file's YAML frontmatter.
 * Returns null if the field is not found or the file doesn't exist.
 */
export function extractGeneratedByVersion(skillFilePath: string): string | null {
  try {
    if (!fs.existsSync(skillFilePath)) {
      return null;
    }

    const content = fs.readFileSync(skillFilePath, 'utf-8');

    // Look for generatedBy in the YAML frontmatter
    const generatedByMatch = content.match(/^\s*generatedBy:\s*["']?([^"'\n]+)["']?\s*$/m);

    if (generatedByMatch && generatedByMatch[1]) {
      return generatedByMatch[1].trim();
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * Gets version status for a tool by reading the first available skill file.
 * Uses ToolProfileRegistry for skillsDir resolution.
 */
export function getToolVersionStatus(
  projectRoot: string,
  toolId: string,
  currentVersion: string
): ToolVersionStatus {
  const skillsDir = resolveSkillsDir(toolId);
  const tool = AI_TOOLS.find((t) => t.value === toolId);
  if (!skillsDir || !tool) {
    return {
      toolId,
      toolName: tool?.name ?? toolId,
      configured: false,
      generatedByVersion: null,
      needsUpdate: false,
    };
  }

  const fullSkillsDir = path.join(projectRoot, skillsDir, 'skills');
  let generatedByVersion: string | null = null;

  // Find the first skill file that exists and read its version
  for (const skillName of SKILL_NAMES) {
    const skillFile = path.join(fullSkillsDir, skillName, 'SKILL.md');
    if (fs.existsSync(skillFile)) {
      generatedByVersion = extractGeneratedByVersion(skillFile);
      break;
    }
  }

  const configured = getToolSkillStatus(projectRoot, toolId).configured;
  const needsUpdate = configured && (generatedByVersion === null || generatedByVersion !== currentVersion);

  return {
    toolId,
    toolName: tool.name,
    configured,
    generatedByVersion,
    needsUpdate,
  };
}

/**
 * Gets all configured tools in the project.
 * Uses ToolProfileRegistry for capability lookup.
 */
export function getConfiguredTools(projectRoot: string): string[] {
  return getToolsWithSkillsSupport()
    .filter((toolId) => getToolSkillStatus(projectRoot, toolId).configured);
}

/**
 * Gets version status for all configured tools.
 */
export function getAllToolVersionStatus(
  projectRoot: string,
  currentVersion: string
): ToolVersionStatus[] {
  const configuredTools = getConfiguredTools(projectRoot);
  return configuredTools.map((toolId) =>
    getToolVersionStatus(projectRoot, toolId, currentVersion)
  );
}
