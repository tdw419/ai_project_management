/**
 * Tool Profile Registry
 *
 * Centralized registry for tool capability profiles.
 * Each tool has a profile that consolidates:
 * - Skills directory and path resolution (from AI_TOOLS)
 * - Command adapter presence (from CommandAdapterRegistry)
 * - Command surface capability (from command-surface resolution)
 * - Workflow-to-skill-dir mapping (from manifest)
 *
 * This registry replaces the need to query AI_TOOLS, CommandAdapterRegistry,
 * and hardcoded maps separately. It is the single source of truth for
 * "what can this tool do?" questions.
 */

import { AI_TOOLS, type AIToolOption, type CommandSurface } from '../config.js';
import { CommandAdapterRegistry } from '../command-generation/index.js';
import { resolveCommandSurface } from '../shared/command-surface.js';
import {
  getManifestEntries,
  type WorkflowManifestEntry,
} from './manifest.js';
import type {
  ToolProfile,
  SkillProfile,
  CommandProfile,
  WorkflowSkillDirMap,
} from './tool-profile-types.js';

// ---------------------------------------------------------------------------
// Workflow skill-dir mapping (manifest-derived, replaces hardcoded maps)
// ---------------------------------------------------------------------------

let _workflowSkillDirMap: WorkflowSkillDirMap | null = null;

/**
 * Returns the mapping from workflow IDs to skill directory names.
 * Derived from the canonical manifest — no hardcoded values.
 * Memoized after first call.
 */
export function getWorkflowSkillDirMap(): WorkflowSkillDirMap {
  if (_workflowSkillDirMap) return _workflowSkillDirMap;

  const entries = getManifestEntries();
  const map = new Map<string, string>();
  for (const entry of entries) {
    map.set(entry.workflowId, entry.skill.dirName);
  }
  _workflowSkillDirMap = map;
  return map;
}

/**
 * Looks up a skill directory name by workflow ID.
 * Returns undefined if the workflow is not in the manifest.
 */
export function getSkillDirForWorkflow(workflowId: string): string | undefined {
  return getWorkflowSkillDirMap().get(workflowId);
}

// ---------------------------------------------------------------------------
// Tool profile construction
// ---------------------------------------------------------------------------

/**
 * Builds a SkillProfile from an AIToolOption.
 */
function buildSkillProfile(tool: AIToolOption): SkillProfile {
  if (!tool.skillsDir) {
    return { supported: false };
  }
  return {
    supported: true,
    skillsDir: tool.skillsDir,
    scopeSupport: tool.scopeSupport,
  };
}

/**
 * Builds a CommandProfile from an AIToolOption and adapter presence.
 */
function buildCommandProfile(tool: AIToolOption): CommandProfile {
  const hasAdapter = CommandAdapterRegistry.has(tool.value);
  const surface = resolveCommandSurface(tool.value, hasAdapter);
  return {
    surface,
    hasAdapter,
    scopeSupport: tool.scopeSupport,
  };
}

/**
 * Builds a complete ToolProfile from an AIToolOption.
 */
function buildToolProfile(tool: AIToolOption): ToolProfile {
  return {
    toolId: tool.value,
    name: tool.name,
    available: tool.available,
    skill: buildSkillProfile(tool),
    command: buildCommandProfile(tool),
    successLabel: tool.successLabel,
  };
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

let _profiles: Map<string, ToolProfile> | null = null;

/**
 * Returns all tool profiles, indexed by toolId.
 * Memoized after first call.
 */
function getAllProfiles(): Map<string, ToolProfile> {
  if (_profiles) return _profiles;

  const map = new Map<string, ToolProfile>();
  for (const tool of AI_TOOLS) {
    map.set(tool.value, buildToolProfile(tool));
  }
  _profiles = map;
  return map;
}

/**
 * Invalidates the profile cache.
 * Useful in tests where AI_TOOLS or adapter registrations may change.
 */
export function invalidateToolProfileCache(): void {
  _profiles = null;
  _workflowSkillDirMap = null;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Get a tool profile by tool ID.
 * Returns undefined if the tool is not registered.
 */
export function getToolProfile(toolId: string): ToolProfile | undefined {
  return getAllProfiles().get(toolId);
}

/**
 * Get all registered tool profiles.
 */
export function getAllToolProfiles(): ToolProfile[] {
  return Array.from(getAllProfiles().values());
}

/**
 * Get tool IDs for tools that support skill generation.
 * This replaces the pattern `AI_TOOLS.filter(t => t.skillsDir).map(t => t.value)`.
 */
export function getToolsWithSkillsSupport(): string[] {
  return getAllToolProfiles()
    .filter((p) => p.skill.supported)
    .map((p) => p.toolId);
}

/**
 * Get tool IDs for tools that have a command adapter registered.
 */
export function getToolsWithCommandAdapter(): string[] {
  return getAllToolProfiles()
    .filter((p) => p.command.hasAdapter)
    .map((p) => p.toolId);
}

/**
 * Get tool IDs for tools that support skill generation and are available.
 */
export function getAvailableToolsWithSkills(): ToolProfile[] {
  return getAllToolProfiles().filter((p) => p.available && p.skill.supported);
}

/**
 * Resolve the skills directory path for a tool relative to a project root.
 * Returns undefined if the tool does not support skills.
 */
export function resolveSkillsDir(toolId: string): string | undefined {
  const profile = getToolProfile(toolId);
  return profile?.skill.skillsDir;
}

/**
 * Resolve the full skill path for a workflow under a tool's skills directory.
 * Returns undefined if the tool doesn't support skills or the workflow has no skill dir.
 */
export function resolveSkillPath(
  toolId: string,
  workflowId: string
): string | undefined {
  const skillsDir = resolveSkillsDir(toolId);
  const skillDirName = getSkillDirForWorkflow(workflowId);
  if (!skillsDir || !skillDirName) return undefined;
  return `${skillsDir}/skills/${skillDirName}`;
}
