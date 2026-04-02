/**
 * Executor -- runs a Hermes agent against a project task.
 *
 * Replaces AIPM v2's GroundedDriver + the subprocess management in loop.py.
 * Handles: trust boundary (snapshot/restore), agent invocation, output capture.
 */

import { execFile } from 'child_process';
import { mkdir, readFile, writeFile, cp, rm } from 'fs/promises';
import { join, resolve } from 'path';
import { existsSync } from 'fs';
import { createHash } from 'crypto';
import type { ProjectConfig } from '../models/config.js';
import type { Strategy } from '../models/outcome.js';

export interface ExecuteOptions {
  prompt: string;
  strategy: Strategy;
  model: string;
  /** Tools to enable for the agent */
  tools: string[];
  /** Skills to load */
  skills: string[];
  /** Attempt number (for retry strategies) */
  attemptNumber: number;
  /** Branch name for this task */
  branch?: string;
}

export interface ExecuteResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  /** Duration in seconds */
  duration: number;
  /** Output saved to file for debugging */
  outputFile?: string;
}

export class Executor {
  private hermesBin: string;
  private outputDir: string;

  constructor(hermesBin?: string, outputDir?: string) {
    this.hermesBin = hermesBin || 'hermes';
    this.outputDir = outputDir || '/tmp/openspec_aipm_outputs';
  }

  /**
   * Run a hermes agent with the given prompt.
   */
  async execute(
    project: ProjectConfig,
    options: ExecuteOptions,
  ): Promise<ExecuteResult> {
    await mkdir(this.outputDir, { recursive: true });

    const startTime = Date.now();
    const args = this.buildArgs(options);

    return new Promise((resolve) => {
      execFile(
        this.hermesBin,
        args,
        {
          cwd: project.path,
          timeout: 600_000, // 10 min max
          maxBuffer: 10 * 1024 * 1024,
        },
        async (err, stdout, stderr) => {
          const duration = Math.round((Date.now() - startTime) / 1000);
          let exitCode = err ? (err as any).code || 1 : 0;

          // Detect API failures that hermes masks with exit 0
          const raw = stdout + '\n' + stderr;
          if (exitCode === 0 && this.detectApiFailure(raw)) {
            exitCode = 2;
          }

          // Save output for debugging
          const hash = createHash('md5')
            .update(`${project.name}:${Date.now()}`)
            .digest('hex')
            .slice(0, 8);
          const outputFile = join(
            this.outputDir,
            `${project.name}_${hash}.txt`
          );
          try {
            await writeFile(outputFile, raw.slice(0, 100_000));
          } catch { /* best effort */ }

          resolve({
            exitCode,
            stdout,
            stderr,
            duration,
            outputFile,
          });
        },
      );
    });
  }

  private buildArgs(options: ExecuteOptions): string[] {
    const args = [
      'chat', '-q',
      options.prompt,
      '-Q', '--yolo',
      '-t', options.tools.join(','),
      '-m', options.model,
    ];

    if (options.skills.length > 0) {
      args.push('-s', options.skills.join(','));
    }

    return args;
  }

  /**
   * Hermes exits 0 even when API calls fail completely.
   * Detect this by checking for final failure signatures.
   */
  private detectApiFailure(output: string): boolean {
    const finalFailureSigs = [
      'Max retries (3) exceeded',
      'API call failed after 3 retries',
    ];
    const hasFinalFailure = finalFailureSigs.some(s => output.includes(s));
    if (!hasFinalFailure) return false;

    // Check if agent actually did work despite the error
    const workEvidence = [
      'preparing terminal',
      'write_file',
      '$         ',
      'file changed',
    ];
    return !workEvidence.some(e => output.includes(e));
  }
}
