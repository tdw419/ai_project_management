/**
 * Skill Generation Utilities
 *
 * Shared utilities for generating skill and command files.
 * All workflow data is now derived from the canonical manifest registry.
 */

import {
  getManifestEntries,
  type WorkflowManifestEntry,
} from '../templates/manifest.js';
import type { SkillTemplate } from '../templates/types.js';
import type { CommandContent } from '../command-generation/index.js';
import {
  getTransformPipeline,
  type TransformContext,
} from '../templates/transform-pipeline.js';

/**
 * Skill template with directory name and workflow ID mapping.
 */
export interface SkillTemplateEntry {
  template: SkillTemplate;
  dirName: string;
  workflowId: string;
}

/**
 * Command template with ID mapping.
 */
export interface CommandTemplateEntry {
  template: ReturnType<NonNullable<WorkflowManifestEntry['command']>['getTemplate']>;
  id: string;
}

/**
 * Gets skill templates with their directory names, optionally filtered by workflow IDs.
 *
 * @param workflowFilter - If provided, only return templates whose workflowId is in this array
 */
export function getSkillTemplates(workflowFilter?: readonly string[]): SkillTemplateEntry[] {
  const entries = getManifestEntries(workflowFilter);
  return entries.map((entry) => ({
    template: entry.skill.getTemplate(),
    dirName: entry.skill.dirName,
    workflowId: entry.workflowId,
  }));
}

/**
 * Gets command templates with their IDs, optionally filtered by workflow IDs.
 *
 * @param workflowFilter - If provided, only return templates whose id is in this array
 */
export function getCommandTemplates(workflowFilter?: readonly string[]): CommandTemplateEntry[] {
  const entries = getManifestEntries(workflowFilter);
  return entries
    .filter((entry) => entry.command != null)
    .map((entry) => ({
      template: entry.command!.getTemplate(),
      id: entry.workflowId,
    }));
}

/**
 * Converts command templates to CommandContent array, optionally filtered by workflow IDs.
 *
 * @param workflowFilter - If provided, only return contents whose id is in this array
 */
export function getCommandContents(workflowFilter?: readonly string[]): CommandContent[] {
  const commandTemplates = getCommandTemplates(workflowFilter);
  return commandTemplates.map(({ template, id }) => ({
    id,
    name: template.name,
    description: template.description,
    category: template.category,
    tags: template.tags,
    body: template.content,
  }));
}

/**
 * Generates skill file content with YAML frontmatter.
 *
 * @param template - The skill template
 * @param generatedByVersion - The OpenSpec version to embed in the file
 * @param transformInstructions - Optional callback to transform the instructions content
 */
export function generateSkillContent(
  template: SkillTemplate,
  generatedByVersion: string,
  transformInstructions?: (instructions: string) => string
): string {
  const instructions = transformInstructions
    ? transformInstructions(template.instructions)
    : template.instructions;

  return `---
name: ${template.name}
description: ${template.description}
license: ${template.license || 'MIT'}
compatibility: ${template.compatibility || 'Requires openspec CLI.'}
metadata:
  author: ${template.metadata?.author || 'openspec'}
  version: "${template.metadata?.version || '1.0'}"
  generatedBy: "${generatedByVersion}"
---

${instructions}
`;
}

/**
 * Generates skill file content with YAML frontmatter, applying transforms
 * from the transform pipeline.
 *
 * This is the pipeline-native equivalent of `generateSkillContent`.
 * It should be preferred over the ad-hoc `transformInstructions` parameter.
 *
 * @param template - The skill template
 * @param generatedByVersion - The OpenSpec version to embed in the file
 * @param ctx - The transform context (toolId, workflowId)
 */
export function generateSkillContentWithPipeline(
  template: SkillTemplate,
  generatedByVersion: string,
  ctx: TransformContext,
): string {
  const pipeline = getTransformPipeline();
  const rawContent = generateSkillContent(template, generatedByVersion);
  const result = pipeline.runForSkill(rawContent, ctx);
  return result.content;
}
