/**
 * SEC-5.4: Expanded Parity Tests for Workflow/Tool Matrix
 *
 * Validates that the manifest-derived skill/command generation produces
 * consistent, complete output for a representative matrix of workflows
 * and tools. Tests the full pipeline from manifest -> skill templates ->
 * command contents -> generated output.
 */

import { createHash } from 'node:crypto';
import { describe, expect, it, beforeEach } from 'vitest';

import { AI_TOOLS } from '../../../src/core/config.js';
import { CommandAdapterRegistry } from '../../../src/core/command-generation/index.js';
import {
  getSkillTemplates,
  getCommandTemplates,
  getCommandContents,
  generateSkillContentWithPipeline,
} from '../../../src/core/shared/skill-generation.js';
import {
  WORKFLOW_MANIFEST,
  getManifestEntries,
  getWorkflowIds,
  getSkillDirNames,
  getCommandIds,
} from '../../../src/core/templates/manifest.js';
import {
  getWorkflowSkillDirMap,
  getToolProfile,
  invalidateToolProfileCache,
} from '../../../src/core/templates/tool-profile-registry.js';

function hashContent(content: string): string {
  return createHash('sha256').update(content).digest('hex');
}

describe('SEC-5.4: Workflow/tool matrix parity', () => {
  beforeEach(() => {
    invalidateToolProfileCache();
  });

  describe('manifest <-> skill-generation parity', () => {
    it('getSkillTemplates count matches deployable manifest entries count', () => {
      const entries = getManifestEntries();
      const templates = getSkillTemplates();
      expect(templates.length).toBe(entries.length);
    });

    it('getCommandTemplates count matches deployable entries with commands', () => {
      const entries = getManifestEntries().filter((e) => e.command != null);
      const templates = getCommandTemplates();
      expect(templates.length).toBe(entries.length);
    });

    it('getCommandContents count matches command templates count', () => {
      const templates = getCommandTemplates();
      const contents = getCommandContents();
      expect(contents.length).toBe(templates.length);
    });

    it('every manifest skill dirName should appear in getSkillTemplates', () => {
      const entries = getManifestEntries();
      const templates = getSkillTemplates();
      const dirNames = new Set(templates.map((t) => t.dirName));

      for (const entry of entries) {
        expect(
          dirNames.has(entry.skill.dirName),
          `dirName "${entry.skill.dirName}" missing from getSkillTemplates`
        ).toBe(true);
      }
    });

    it('every manifest workflowId with command should appear in getCommandTemplates', () => {
      const entries = getManifestEntries().filter((e) => e.command != null);
      const templates = getCommandTemplates();
      const ids = new Set(templates.map((t) => t.id));

      for (const entry of entries) {
        expect(
          ids.has(entry.workflowId),
          `workflowId "${entry.workflowId}" missing from getCommandTemplates`
        ).toBe(true);
      }
    });
  });

  describe('skill content stability across tools', () => {
    const representativeTools = ['claude', 'cursor', 'opencode', 'gemini', 'codex'];

    it('skill content for non-opencode tools should be identical', () => {
      const templates = getSkillTemplates();
      const nonOpenCodeTools = representativeTools.filter((t) => t !== 'opencode');

      for (const template of templates) {
        const hashes = nonOpenCodeTools.map((toolId) =>
          hashContent(
            generateSkillContentWithPipeline(template.template, 'TEST-VER', {
              toolId,
              workflowId: template.workflowId,
            })
          )
        );
        // All non-opencode tools should produce the same content
        const uniqueHashes = new Set(hashes);
        expect(
          uniqueHashes.size,
          `skill "${template.dirName}" should be identical across non-opencode tools`
        ).toBe(1);
      }
    });

    it('skill content for opencode should differ from non-opencode tools', () => {
      const templates = getSkillTemplates();

      // Only test templates that contain /opsx: references
      const templatesWithRefs = templates.filter(
        (t) => t.template.instructions.includes('/opsx:')
      );

      if (templatesWithRefs.length > 0) {
        const template = templatesWithRefs[0];
        const opencodeContent = generateSkillContentWithPipeline(
          template.template,
          'TEST-VER',
          { toolId: 'opencode', workflowId: template.workflowId }
        );
        const claudeContent = generateSkillContentWithPipeline(
          template.template,
          'TEST-VER',
          { toolId: 'claude', workflowId: template.workflowId }
        );
        expect(opencodeContent).not.toBe(claudeContent);
        expect(opencodeContent).toContain('/opsx-');
      }
    });

    it('every skill content should have valid YAML frontmatter', () => {
      const templates = getSkillTemplates();

      for (const toolId of representativeTools) {
        for (const template of templates) {
          const content = generateSkillContentWithPipeline(
            template.template,
            'TEST-VER',
            { toolId, workflowId: template.workflowId }
          );

          expect(content.startsWith('---\n')).toBe(true);
          expect(content).toContain('name:');
          expect(content).toContain('description:');
          expect(content).toContain('generatedBy: "TEST-VER"');
        }
      }
    });
  });

  describe('command generation parity', () => {
    it('every adapter should produce output for all command contents', () => {
      const contents = getCommandContents();
      const adapters = CommandAdapterRegistry.getAll();

      for (const adapter of adapters) {
        for (const content of contents) {
          const filePath = adapter.getFilePath(content.id);
          const fileContent = adapter.formatFile(content);

          expect(filePath).toBeTruthy();
          expect(fileContent).toBeTruthy();
          expect(fileContent.length).toBeGreaterThan(0);
        }
      }
    });

    it('command contents should have matching fields with command templates', () => {
      const templates = getCommandTemplates();
      const contents = getCommandContents();

      const templateMap = new Map(templates.map((t) => [t.id, t.template]));

      for (const content of contents) {
        const tmpl = templateMap.get(content.id);
        expect(tmpl, `command content id "${content.id}" should have matching template`).toBeDefined();
        expect(content.name).toBe(tmpl!.name);
        expect(content.description).toBe(tmpl!.description);
        expect(content.category).toBe(tmpl!.category);
        expect(content.tags).toEqual(tmpl!.tags);
        expect(content.body).toBe(tmpl!.content);
      }
    });
  });

  describe('workflow skill-dir map consistency', () => {
    it('map should be consistent with manifest', () => {
      const map = getWorkflowSkillDirMap();
      const entries = getManifestEntries();

      expect(map.size).toBe(entries.length);

      for (const entry of entries) {
        expect(map.get(entry.workflowId)).toBe(entry.skill.dirName);
      }
    });

    it('every tool profile with skillsDir should resolve all skill paths', () => {
      const entries = getManifestEntries();

      for (const tool of AI_TOOLS) {
        if (!tool.skillsDir) continue;
        const profile = getToolProfile(tool.value);
        expect(profile).toBeDefined();
        expect(profile!.skill.supported).toBe(true);

        for (const entry of entries) {
          // Just verify the path can be composed
          const expectedPath = `${tool.skillsDir}/skills/${entry.skill.dirName}`;
          // The path should be a valid relative path
          expect(expectedPath).toMatch(/^\.[a-z0-9-]+\/skills\/openspec-/);
        }
      }
    });
  });

  describe('deterministic output', () => {
    it('getSkillTemplates should return entries in the same order across calls', () => {
      const a = getSkillTemplates();
      const b = getSkillTemplates();
      const aIds = a.map((t) => t.workflowId);
      const bIds = b.map((t) => t.workflowId);
      expect(aIds).toEqual(bIds);
    });

    it('getCommandContents should return entries in the same order across calls', () => {
      const a = getCommandContents();
      const b = getCommandContents();
      const aIds = a.map((c) => c.id);
      const bIds = b.map((c) => c.id);
      expect(aIds).toEqual(bIds);
    });

    it('generated content hashes should be stable across calls', () => {
      const templates = getSkillTemplates();
      const hashes1 = templates.map((t) =>
        hashContent(
          generateSkillContentWithPipeline(t.template, 'STABLE-TEST', {
            toolId: 'claude',
            workflowId: t.workflowId,
          })
        )
      );
      const hashes2 = templates.map((t) =>
        hashContent(
          generateSkillContentWithPipeline(t.template, 'STABLE-TEST', {
            toolId: 'claude',
            workflowId: t.workflowId,
          })
        )
      );
      expect(hashes1).toEqual(hashes2);
    });
  });
});
