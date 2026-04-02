/**
 * SEC-5.2: Tool-Profile Consistency Tests
 *
 * Validates that tool profiles, adapter registrations, and skillsDir
 * support are consistent across AI_TOOLS, CommandAdapterRegistry,
 * and ToolProfileRegistry.
 */

import { describe, expect, it, beforeEach } from 'vitest';
import { AI_TOOLS } from '../../../src/core/config.js';
import { CommandAdapterRegistry } from '../../../src/core/command-generation/index.js';
import {
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
} from '../../../src/core/templates/tool-profile-registry.js';
import { getSkillDirNames } from '../../../src/core/templates/manifest.js';

describe('SEC-5.2: Tool-profile consistency', () => {
  beforeEach(() => {
    invalidateToolProfileCache();
  });

  describe('profile registry coverage', () => {
    it('every AI_TOOLS entry should have a profile', () => {
      const profiles = getAllToolProfiles();
      expect(profiles.length).toBe(AI_TOOLS.length);

      for (const tool of AI_TOOLS) {
        const profile = getToolProfile(tool.value);
        expect(profile, `profile for "${tool.value}"`).toBeDefined();
        expect(profile!.toolId).toBe(tool.value);
      }
    });

    it('profile names should match AI_TOOLS names', () => {
      for (const tool of AI_TOOLS) {
        const profile = getToolProfile(tool.value);
        expect(profile!.name).toBe(tool.name);
      }
    });

    it('profile availability should match AI_TOOLS available flag', () => {
      for (const tool of AI_TOOLS) {
        const profile = getToolProfile(tool.value);
        expect(profile!.available).toBe(tool.available);
      }
    });
  });

  describe('skillsDir consistency', () => {
    it('tools with skillsDir should report skill.supported=true', () => {
      for (const tool of AI_TOOLS) {
        const profile = getToolProfile(tool.value);
        if (tool.skillsDir) {
          expect(profile!.skill.supported).toBe(true);
          expect(profile!.skill.skillsDir).toBe(tool.skillsDir);
        } else {
          expect(profile!.skill.supported).toBe(false);
        }
      }
    });

    it('getToolsWithSkillsSupport should match AI_TOOLS with skillsDir', () => {
      const expected = AI_TOOLS.filter((t) => t.skillsDir).map((t) => t.value).sort();
      const actual = getToolsWithSkillsSupport().sort();
      expect(actual).toEqual(expected);
    });

    it('resolveSkillsDir should return skillsDir for supported tools', () => {
      for (const tool of AI_TOOLS) {
        const resolved = resolveSkillsDir(tool.value);
        expect(resolved).toBe(tool.skillsDir);
      }
    });

    it('resolveSkillsDir should return undefined for tools without skillsDir', () => {
      // 'agents' has no skillsDir
      const resolved = resolveSkillsDir('agents');
      expect(resolved).toBeUndefined();
    });
  });

  describe('adapter consistency', () => {
    it('getToolsWithCommandAdapter should list all tools with registered adapters', () => {
      const adapterTools = getToolsWithCommandAdapter();
      expect(adapterTools.length).toBeGreaterThan(0);

      for (const toolId of adapterTools) {
        expect(CommandAdapterRegistry.has(toolId)).toBe(true);
      }
    });

    it('every registered adapter toolId should have a matching AI_TOOLS entry', () => {
      const allAdapters = CommandAdapterRegistry.getAll();
      const aiToolValues = new Set(AI_TOOLS.map((t) => t.value));

      for (const adapter of allAdapters) {
        expect(
          aiToolValues.has(adapter.toolId),
          `adapter "${adapter.toolId}" not in AI_TOOLS`
        ).toBe(true);
      }
    });

    it('tools with adapter should report command.hasAdapter=true', () => {
      const profiles = getAllToolProfiles();
      for (const profile of profiles) {
        const hasAdapter = CommandAdapterRegistry.has(profile.toolId);
        expect(profile.command.hasAdapter).toBe(hasAdapter);
      }
    });
  });

  describe('workflow skill-dir map', () => {
    it('getWorkflowSkillDirMap should cover all deployable workflow IDs', () => {
      const map = getWorkflowSkillDirMap();
      const dirNames = getSkillDirNames();

      expect(map.size).toBe(dirNames.length);
      for (const dirName of dirNames) {
        const found = Array.from(map.values()).includes(dirName);
        expect(found, `dirName "${dirName}" not in workflow skill-dir map`).toBe(true);
      }
    });

    it('getSkillDirForWorkflow should return correct dirName', () => {
      // Test known mappings
      expect(getSkillDirForWorkflow('explore')).toBe('openspec-explore');
      expect(getSkillDirForWorkflow('new')).toBe('openspec-new-change');
      expect(getSkillDirForWorkflow('apply')).toBe('openspec-apply-change');
      expect(getSkillDirForWorkflow('feedback')).toBeUndefined(); // non-deployable
    });

    it('resolveSkillPath should compose skillsDir + skills + dirName', () => {
      // Claude has skillsDir '.claude', explore has dirName 'openspec-explore'
      const path = resolveSkillPath('claude', 'explore');
      expect(path).toBe('.claude/skills/openspec-explore');
    });

    it('resolveSkillPath should return undefined for tool without skillsDir', () => {
      const path = resolveSkillPath('agents', 'explore');
      expect(path).toBeUndefined();
    });

    it('resolveSkillPath should return undefined for unknown workflow', () => {
      const path = resolveSkillPath('claude', 'nonexistent-workflow');
      expect(path).toBeUndefined();
    });
  });

  describe('available tools with skills', () => {
    it('getAvailableToolsWithSkills should only return available tools with skillsDir', () => {
      const available = getAvailableToolsWithSkills();
      for (const profile of available) {
        expect(profile.available).toBe(true);
        expect(profile.skill.supported).toBe(true);
      }
    });

    it('agents tool should not be in available tools with skills', () => {
      const available = getAvailableToolsWithSkills();
      const agents = available.find((p) => p.toolId === 'agents');
      expect(agents).toBeUndefined();
    });
  });
});
