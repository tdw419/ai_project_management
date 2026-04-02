/**
 * Scheduler -- the main orchestration loop.
 *
 * Replaces AIPM v2's run_once() + run_forever(). Simplified:
 * 1. For each project, ask OpenSpec for the next pending task
 * 2. Build a prompt, select a model, run the agent
 * 3. Parse the outcome, update spec status
 * 4. Repeat
 */

import { OpenSpecBridge } from './openspec-bridge.js';
import { Executor } from './executor.js';
import { parseOutcome } from './outcome-parser.js';
import { buildPrompt } from './prompt-builder.js';
import { selectModel, recordOutcome } from './model-router.js';
import { SessionMiner } from './output-management/session-miner.js';
import { LearningsExtractor } from './output-management/learnings-extractor.js';
import { OutcomeCorrelator } from './output-management/outcome-correlator.js';
import { SpecGenerator } from './spec-generator.js';
import type { AipmConfig, ProjectConfig } from '../models/config.js';
import { Strategy } from '../models/outcome.js';
import { execFile } from 'child_process';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { join } from 'path';

export class Scheduler {
  private config: AipmConfig;
  private bridge: OpenSpecBridge;
  private executor: Executor;
  private miner: SessionMiner;
  private extractor: LearningsExtractor;
  private correlator: OutcomeCorrelator;
  private specGenerator: SpecGenerator;
  private running = false;
  private activeAgents = new Map<string, Promise<void>>();
  private lastSpecGeneration = new Map<string, number>();

  constructor(config: AipmConfig) {
    this.config = config;
    this.bridge = new OpenSpecBridge(config.openspecBin);
    this.executor = new Executor(config.hermesBin, join(config.dataDir, 'outputs'));
    this.miner = new SessionMiner();
    this.extractor = new LearningsExtractor('/tmp/openspec_aipm/learnings');
    this.correlator = new OutcomeCorrelator();
    this.specGenerator = new SpecGenerator(this.executor, this.bridge, this.config.cloudModel);
  }

  /**
   * Run a single cycle across all projects.
   */
  async runOnce(): Promise<void> {
    console.log(`--- Cycle ${new Date().toISOString()} ---`);

    // Refresh global learnings for all projects
    try {
      const recent = this.miner.mineSessions({
        since: new Date(Date.now() - 3600 * 1000), // last hour
        limit: 100,
      });

      if (recent.length > 0) {
        console.log(`  Refreshing global learnings from ${recent.length} recent sessions...`);
        // Group by project
        const byProject = new Map<string, any[]>();
        for (const s of recent) {
          const project = s.prompt?.project ?? 'unknown';
          if (!byProject.has(project)) byProject.set(project, []);
          byProject.get(project)!.push(s);
        }

        for (const [project, sessions] of byProject.entries()) {
          const learnings = this.extractor.extractFromSessions(sessions);
          if (learnings.length > 0) {
            await this.extractor.saveLearnings(project, learnings);
          }
        }
      }
    } catch (err) {
      console.error(`  Warning: failed to refresh global learnings: ${err}`);
    }

    for (const project of this.config.projects) {
      // Skip if agent already running for this project
      if (this.activeAgents.has(project.name)) continue;

      // Get next task from OpenSpec
      const change = await this.bridge.getNextPendingTask(project.path);
      if (!change) {
        // Spec Generation Cooldown: 1 hour
        const lastGen = this.lastSpecGeneration.get(project.name) || 0;
        const cooldownMs = 60 * 60 * 1000;
        const timeSinceLastGen = Date.now() - lastGen;

        if (timeSinceLastGen < cooldownMs) {
          const minutesLeft = Math.ceil((cooldownMs - timeSinceLastGen) / 60000);
          console.log(`  ${project.name}: No pending tasks. SpecGenerator cooling down (${minutesLeft}m left).`);
          continue;
        }

        console.log(`  ${project.name}: No pending tasks. Calling SpecGenerator...`);
        this.lastSpecGeneration.set(project.name, Date.now());
        await this.specGenerator.generateNextSpec(project);
        continue;
      }

      const section = change.sections[0];
      console.log(
        `  ${project.name}: starting spec task ${change.name}/SEC-${section.id} - ${section.title.slice(0, 50)}`
      );

      // Determine strategy and attempt number from history
      const history = this.correlator.getTaskHistory(project.name, change.name, section.id);
      let strategy = Strategy.FRESH;
      let attemptNumber = 1;

      if (history.length > 0) {
        attemptNumber = history.length + 1;
        const lastOutcome = history[0]; // descending by timestamp
        
        // Select strategy based on last failure mode
        if (lastOutcome.outcomeStatus === 'failed') {
          strategy = attemptNumber >= 4 ? Strategy.DIFFERENT_APPROACH : Strategy.RETRY;
        } else if (lastOutcome.outcomeStatus === 'no_change') {
          strategy = Strategy.SIMPLIFY;
        } else {
          strategy = Strategy.RETRY;
        }
      }

      // Get test state
      const testsBefore = await this.getTestCounts(project);

      // Select model
      const routing = selectModel(
        project, strategy, attemptNumber,
        this.config.cloudModel, this.config.localModel,
      );
      console.log(`  Routing: ${routing.model} (${routing.reason})`);

      // Build prompt
      const prompt = await buildPrompt(
        {
          project,
          change,
          section,
          testsBefore,
          strategy,
          attemptNumber,
          lastOutcome: history.length > 0 ? `Status: ${history[0].outcomeStatus}` : undefined,
        },
        this.bridge,
      );
      console.log(`  Running: hermes chat (${prompt.length} chars, strategy=${strategy}, attempt=${attemptNumber})`);

      // Run the agent
      const commitBefore = await this.getCommitHash(project.path);
      const result = await this.executor.execute(project, {
        prompt,
        strategy,
        model: routing.model,
        tools: ['terminal', 'file'],
        skills: ['github-issues', 'test-driven-development'],
        attemptNumber,
      });

      // Get after-state
      const testsAfter = await this.getTestCounts(project);
      const commitAfter = await this.getCommitHash(project.path);

      // Parse outcome
      const outcome = await parseOutcome({
        exitCode: result.exitCode,
        projectPath: project.path,
        testsBefore,
        testsAfter,
        protectedFiles: project.protectedFiles,
        commitBefore,
        commitAfter,
      });

      console.log(`  Outcome: ${outcome.summary}`);

      // Update spec based on outcome
      if (outcome.status === 'success') {
        await this.bridge.completeSection(project.path, change.name, section.id);
        console.log(`  Spec task ${change.name}/SEC-${section.id}: COMPLETED`);
      }

      // Record for routing
      recordOutcome(project.name, outcome.status === 'success');
    }
  }

  /**
   * Run forever with the configured interval.
   */
  async runForever(): Promise<void> {
    this.running = true;
    console.log(`AIPM v3 starting with ${this.config.projects.length} projects`);

    while (this.running) {
      try {
        await this.runOnce();
      } catch (err) {
        console.error(`Cycle error: ${err}`);
      }

      // Wait for interval
      await new Promise(r => setTimeout(r, this.config.intervalSeconds * 1000));
    }
  }

  stop(): void {
    this.running = false;
  }

  private async getTestCounts(project: ProjectConfig): Promise<[number, number]> {
    // Run the test command and parse output
    // This is project-specific and needs per-language parsers
    // For now, return [0, 0] as placeholder
    try {
      const result = await new Promise<string>((resolve, reject) => {
        execFile(
          'bash', ['-c', project.testCommand],
          { cwd: project.path, timeout: 60_000 },
          (err, stdout) => {
            if (err) reject(err);
            else resolve(stdout);
          },
        );
      });

      // Parse npm test output: "Tests: N passed, M total"
      const match = result.match(/(\d+)\s+(?:passing|passed).*?(\d+)\s+total/s)
        || result.match(/Tests:\s+\d+\/(\d+).*?(\d+)/s);

      if (match) {
        return [parseInt(match[1]), parseInt(match[2])];
      }
    } catch { /* tests may fail */ }
    return [0, 0];
  }

  private async getCommitHash(projectPath: string): Promise<string> {
    try {
      const result = await new Promise<string>((resolve, reject) => {
        execFile(
          'git', ['rev-parse', 'HEAD'],
          { cwd: projectPath, timeout: 5000 },
          (err, stdout) => {
            if (err) reject(err);
            else resolve(stdout.trim());
          },
        );
      });
      return result;
    } catch {
      return '';
    }
  }
}
