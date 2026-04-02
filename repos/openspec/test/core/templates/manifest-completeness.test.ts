/**
 * SEC-5.1: Manifest Completeness Tests
 *
 * Validates that the workflow manifest has complete metadata,
 * all required fields, consistent command IDs, and valid directory names.
 */

import { describe, expect, it } from 'vitest';
import {
  WORKFLOW_MANIFEST,
  getManifestEntries,
  getWorkflowIds,
  getSkillDirNames,
  getCommandIds,
} from '../../../src/core/templates/manifest.js';
import type { WorkflowManifestEntry } from '../../../src/core/templates/manifest-types.js';

describe('SEC-5.1: Manifest completeness', () => {
  describe('manifest structure', () => {
    it('should have at least 10 workflow entries', () => {
      expect(WORKFLOW_MANIFEST.length).toBeGreaterThanOrEqual(10);
    });

    it('should have unique workflow IDs', () => {
      const ids = WORKFLOW_MANIFEST.map((e) => e.workflowId);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });

    it('every entry should have a workflowId', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        expect(entry.workflowId).toBeTruthy();
        expect(typeof entry.workflowId).toBe('string');
      }
    });

    it('every entry should have a skill descriptor with dirName and getTemplate', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        expect(entry.skill).toBeDefined();
        expect(entry.skill.dirName).toBeTruthy();
        expect(typeof entry.skill.dirName).toBe('string');
        expect(typeof entry.skill.getTemplate).toBe('function');
      }
    });

    it('every skill.dirName should start with "openspec-"', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        expect(entry.skill.dirName).toMatch(/^openspec-/);
      }
    });

    it('every skill.dirName should be unique', () => {
      const dirNames = WORKFLOW_MANIFEST.map((e) => e.skill.dirName);
      const unique = new Set(dirNames);
      expect(unique.size).toBe(dirNames.length);
    });
  });

  describe('command descriptors', () => {
    it('entries with command should have a valid getTemplate function', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        if (entry.command) {
          expect(typeof entry.command.getTemplate).toBe('function');
        }
      }
    });

    it('feedback should have no command descriptor', () => {
      const feedback = WORKFLOW_MANIFEST.find((e) => e.workflowId === 'feedback');
      expect(feedback).toBeDefined();
      expect(feedback!.command).toBeUndefined();
    });

    it('all non-feedback entries should have a command descriptor', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        if (entry.workflowId === 'feedback') continue;
        expect(
          entry.command,
          `workflow "${entry.workflowId}" should have a command descriptor`
        ).toBeDefined();
      }
    });
  });

  describe('template factories return valid objects', () => {
    it('every skill getTemplate should return a valid SkillTemplate', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        const template = entry.skill.getTemplate();
        expect(template.name, `${entry.workflowId} skill name`).toBeTruthy();
        expect(template.description, `${entry.workflowId} skill description`).toBeTruthy();
        expect(template.instructions, `${entry.workflowId} skill instructions`).toBeTruthy();
        expect(typeof template.instructions).toBe('string');
        expect(template.instructions.length).toBeGreaterThan(0);
      }
    });

    it('every command getTemplate should return a valid CommandTemplate', () => {
      for (const entry of WORKFLOW_MANIFEST) {
        if (!entry.command) continue;
        const template = entry.command.getTemplate();
        expect(template.name, `${entry.workflowId} command name`).toBeTruthy();
        expect(template.description, `${entry.workflowId} command description`).toBeTruthy();
        expect(template.category, `${entry.workflowId} command category`).toBeTruthy();
        expect(Array.isArray(template.tags), `${entry.workflowId} command tags`).toBe(true);
        expect(template.content, `${entry.workflowId} command content`).toBeTruthy();
      }
    });
  });

  describe('derived accessors', () => {
    it('getWorkflowIds returns only deployable workflow IDs', () => {
      const ids = getWorkflowIds();
      expect(ids).not.toContain('feedback');
      expect(ids.length).toBeGreaterThan(0);
    });

    it('getSkillDirNames returns only deployable skill dir names', () => {
      const dirs = getSkillDirNames();
      expect(dirs).not.toContain('openspec-feedback');
      expect(dirs.length).toBeGreaterThan(0);
      for (const d of dirs) {
        expect(d).toMatch(/^openspec-/);
      }
    });

    it('getCommandIds returns only deployable entries with commands', () => {
      const cmdIds = getCommandIds();
      expect(cmdIds).not.toContain('feedback');
      // feedback has no command, so it should not appear
      for (const id of cmdIds) {
        const entry = WORKFLOW_MANIFEST.find((e) => e.workflowId === id);
        expect(entry).toBeDefined();
        expect(entry!.command).toBeDefined();
        expect(entry!.deployable).not.toBe(false);
      }
    });

    it('getManifestEntries without filter returns all deployable entries', () => {
      const entries = getManifestEntries();
      const feedbackEntry = entries.find((e) => e.workflowId === 'feedback');
      expect(feedbackEntry).toBeUndefined();
    });

    it('getManifestEntries with filter returns matching entries', () => {
      const entries = getManifestEntries(['explore', 'apply']);
      expect(entries).toHaveLength(2);
      const ids = entries.map((e) => e.workflowId);
      expect(ids).toContain('explore');
      expect(ids).toContain('apply');
    });

    it('getManifestEntries with filter excludes non-deployable entries', () => {
      const entries = getManifestEntries(['feedback']);
      expect(entries).toHaveLength(0);
    });
  });
});
