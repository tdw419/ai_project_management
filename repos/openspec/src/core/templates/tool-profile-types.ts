/**
 * Tool Profile Types
 *
 * Centralized type definitions for tool capability profiles.
 * Each tool has a profile that declares its capabilities for skill
 * and command generation, derived from the union of AI_TOOLS config,
 * CommandAdapterRegistry, and manifest metadata.
 */

import type { CommandSurface, InstallScope, ToolInstallScopeSupport } from '../config.js';
import type { WorkflowManifestEntry } from './manifest-types.js';

/**
 * Describes the skill resolution info for a tool.
 * Derived from AI_TOOLS.skillsDir and manifest skill dir names.
 */
export interface SkillProfile {
  /** Whether this tool supports skill generation */
  supported: boolean;
  /** The tool's skill base directory relative to project root (e.g., '.claude') */
  skillsDir?: string;
  /** Install scopes supported for skills */
  scopeSupport?: ToolInstallScopeSupport;
}

/**
 * Describes the command resolution info for a tool.
 * Derived from CommandAdapterRegistry and command surface inference.
 */
export interface CommandProfile {
  /** The resolved command surface type */
  surface: CommandSurface;
  /** Whether this tool has a registered command adapter */
  hasAdapter: boolean;
  /** Install scopes supported for commands */
  scopeSupport?: ToolInstallScopeSupport;
}

/**
 * A complete tool profile entry.
 * Consolidates all capability information for a single tool into
 * one place, replacing the need to query AI_TOOLS, CommandAdapterRegistry,
 * and command-surface.ts separately.
 */
export interface ToolProfile {
  /** Tool identifier (e.g., 'claude', 'cursor') */
  toolId: string;
  /** Human-readable display name */
  name: string;
  /** Whether the tool is available for selection */
  available: boolean;
  /** Skill capability profile */
  skill: SkillProfile;
  /** Command capability profile */
  command: CommandProfile;
  /** Success label shown in CLI output */
  successLabel?: string;
}

/**
 * Maps workflow IDs to their skill directory names.
 * Derived from the canonical manifest registry.
 */
export type WorkflowSkillDirMap = ReadonlyMap<string, string>;

/**
 * Resolution result for looking up a tool's profile.
 */
export interface ToolProfileResolution {
  /** The resolved tool profile */
  profile: ToolProfile;
  /** Whether the tool supports skill generation */
  canGenerateSkills: boolean;
  /** Whether the tool supports command generation */
  canGenerateCommands: boolean;
}
