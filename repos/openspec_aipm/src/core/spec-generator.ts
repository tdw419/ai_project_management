import { Executor } from './executor.js';
import { OpenSpecBridge } from './openspec-bridge.js';
import type { ProjectConfig } from '../models/config.js';
import { Strategy } from '../models/outcome.js';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import { join } from 'path';

export class SpecGenerator {
  private JSON_START_MARKER = '<|SPEC_JSON_START|>';
  private JSON_END_MARKER = '<|SPEC_JSON_END|>';

  constructor(
    private executor: Executor,
    private bridge: OpenSpecBridge,
    private cloudModel: string
  ) {}

  /**
   * Run an agent to analyze the project and generate a new OpenSpec change.
   */
  async generateNextSpec(project: ProjectConfig): Promise<boolean> {
    console.log(`  [SpecGenerator] Analyzing project state and learnings to draft new spec...`);

    // Build context for the model
    let learningsContext = '';
    const globalLearningsPath = `/tmp/openspec_aipm/learnings/${project.name}/summary.md`;
    if (existsSync(globalLearningsPath)) {
      const globalLearnings = await readFile(globalLearningsPath, 'utf-8');
      if (globalLearnings.trim()) {
        learningsContext = `\n### PROJECT LEARNINGS\n${globalLearnings.trim()}\n`;
      }
    }

    const prompt = `You are a Principal Staff Engineer planning the next iteration of the project.
### PROJECT: ${project.name}
Path: ${project.path}
Language: ${project.language}
${learningsContext}
INSTRUCTIONS:
1. Explore the codebase to understand its current state, architecture, and gaps.
2. Based on the code and learnings, propose ONE new logical feature, architectural improvement, or technical debt reduction.
3. You MUST respond with ONLY valid JSON matching this exact schema.
4. Wrap your JSON response in the following markers: ${this.JSON_START_MARKER} and ${this.JSON_END_MARKER}.

{
  "slug": "kebab-case-short-name",
  "proposal": {
    "title": "Human readable title",
    "summary": "Why this is needed and what it does",
    "dependencies": "Any prerequisites"
  },
  "tasks": {
    "sections": [
      {
        "title": "Phase 1: Setup",
        "steps": ["Step 1 description", "Step 2 description"]
      }
    ]
  }
}
`;

    // Run the agent to generate the spec
    const result = await this.executor.execute(project, {
      prompt,
      strategy: Strategy.FRESH,
      model: this.cloudModel,
      tools: ['terminal', 'file'],
      skills: [],
      attemptNumber: 1
    });

    const output = result.stdout + '\n' + result.stderr;
    
    // Robust extraction using markers
    const startIdx = output.lastIndexOf(this.JSON_START_MARKER);
    const endIdx = output.indexOf(this.JSON_END_MARKER, startIdx);

    if (startIdx === -1 || endIdx === -1 || endIdx <= startIdx) {
      console.log(`  [SpecGenerator] Failed: No valid JSON markers found in agent output.`);
      // Fallback: try to find any JSON blob as a last resort
      const fallbackMatch = output.match(/\{[\s\S]*\}/);
      if (!fallbackMatch) return false;
      return await this.processJson(project, fallbackMatch[0]);
    }

    const jsonText = output.slice(startIdx + this.JSON_START_MARKER.length, endIdx).trim();
    return await this.processJson(project, jsonText);
  }

  /**
   * Validate and save the generated spec JSON.
   */
  private async processJson(project: ProjectConfig, jsonText: string): Promise<boolean> {
    try {
      const specData = JSON.parse(jsonText);
      
      // Quality & Integrity Gate
      if (!this.validateSpec(project, specData)) {
        return false;
      }

      console.log(`  [SpecGenerator] Success: Generated spec '${specData.slug}' (${specData.proposal.title})`);
      
      // Write the new change to disk using the OpenSpecBridge
      await this.bridge.createChange(
        project.path,
        specData.slug,
        specData.proposal,
        specData.tasks
      );
      
      return true;
    } catch (e) {
      console.log(`  [SpecGenerator] Failed to parse generated spec JSON: ${e}`);
      return false;
    }
  }

  /**
   * Validate the spec data structure and content.
   */
  private validateSpec(project: ProjectConfig, data: any): boolean {
    // 1. Structural Check
    if (!data.slug || !data.proposal || !data.tasks) {
      console.log(`  [SpecGenerator] Validation Failed: Missing top-level fields (slug, proposal, tasks).`);
      return false;
    }
    if (!data.proposal.title || !data.proposal.summary) {
      console.log(`  [SpecGenerator] Validation Failed: Missing proposal fields (title, summary).`);
      return false;
    }
    if (!data.tasks.sections || !Array.isArray(data.tasks.sections) || data.tasks.sections.length === 0) {
      console.log(`  [SpecGenerator] Validation Failed: No task sections defined.`);
      return false;
    }

    // 2. Collision Check
    const changeDir = join(project.path, 'openspec', 'changes', data.slug);
    if (existsSync(changeDir)) {
      console.log(`  [SpecGenerator] Validation Failed: Slug '${data.slug}' already exists in ${project.path}.`);
      return false;
    }

    // 3. Non-Empty Check
    const hasSteps = data.tasks.sections.some((s: any) => 
      s.steps && Array.isArray(s.steps) && s.steps.length > 0
    );
    if (!hasSteps) {
      console.log(`  [SpecGenerator] Validation Failed: No implementation steps defined in any section.`);
      return false;
    }

    return true;
  }
}
