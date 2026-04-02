/**
 * Outcome parser -- determines what happened after an agent ran.
 *
 * Replaces AIPM v2's outcome.py. Examines git diff, test counts,
 * and trust violations to classify the result.
 */

import { execFile } from 'child_process';
import { Outcome, OutcomeStatus } from '../models/outcome.js';

export interface ParseOptions {
  exitCode: number;
  projectPath: string;
  /** Test counts before agent ran */
  testsBefore: [number, number];
  /** Test counts after agent ran */
  testsAfter: [number, number];
  /** Protected files that should not be modified */
  protectedFiles: string[];
  /** Commit hash before agent ran */
  commitBefore: string;
  /** Commit hash after agent ran */
  commitAfter: string;
}

export async function parseOutcome(opts: ParseOptions): Promise<Outcome> {
  const { exitCode, testsBefore, testsAfter, commitBefore, commitAfter } = opts;

  // Get file change counts from git
  const filesChanged = await countChangedFiles(opts.projectPath, commitBefore);
  const trustViolations = await detectTrustViolations(
    opts.projectPath, commitBefore, opts.protectedFiles
  );

  // Revert trust violations
  if (trustViolations.length > 0) {
    await revertFiles(opts.projectPath, trustViolations);
  }

  // Classify outcome
  let status: OutcomeStatus;
  let summary: string;

  const [beforePass, beforeTotal] = testsBefore;
  const [afterPass, afterTotal] = testsAfter;
  const testDiff = afterPass - beforePass;

  if (exitCode !== 0) {
    status = OutcomeStatus.FAILED;
    summary = `FAILED (exit ${exitCode}) | tests: ${beforePass}->${afterPass} | files: ${filesChanged}`;
  } else if (filesChanged === 0 && commitBefore === commitAfter) {
    status = OutcomeStatus.NO_CHANGE;
    summary = `NO CHANGE | tests: ${beforePass}->${afterPass}`;
  } else if (testDiff < 0) {
    status = OutcomeStatus.PARTIAL;
    summary = `PARTIAL (tests regressed) | tests: ${beforePass}->${afterPass} | files: ${filesChanged}`;
  } else if (testDiff > 0) {
    status = OutcomeStatus.SUCCESS;
    summary = `SUCCESS (+${testDiff} tests) | tests: ${beforePass}->${afterPass} | files: ${filesChanged}`;
  } else {
    status = OutcomeStatus.SUCCESS;
    summary = `SUCCESS (code landed, tests stable) | tests: ${beforePass}->${afterPass} | files: ${filesChanged}`;
  }

  return {
    status,
    summary,
    exitCode,
    filesChanged,
    testsBefore,
    testsAfter,
    committed: commitBefore !== commitAfter,
    trustViolations,
  };
}

async function countChangedFiles(
  projectPath: string,
  commitBefore: string,
): Promise<number> {
  try {
    const result = await git(projectPath, [
      'diff', '--name-only', commitBefore, 'HEAD',
    ]);
    const files = result.trim().split('\n').filter(Boolean);
    return files.length;
  } catch {
    return 0;
  }
}

async function detectTrustViolations(
  projectPath: string,
  commitBefore: string,
  protectedFiles: string[],
): Promise<string[]> {
  if (protectedFiles.length === 0) return [];

  try {
    const result = await git(projectPath, [
      'diff', '--name-only', commitBefore, 'HEAD',
    ]);
    const changed = result.trim().split('\n').filter(Boolean);
    return changed.filter(f => protectedFiles.includes(f));
  } catch {
    return [];
  }
}

async function revertFiles(
  projectPath: string,
  files: string[],
): Promise<void> {
  for (const file of files) {
    try {
      await git(projectPath, ['checkout', 'HEAD', '--', file]);
    } catch { /* best effort */ }
  }
}

function git(cwd: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile('git', args, { cwd, timeout: 10_000 }, (err, stdout) => {
      if (err) reject(err);
      else resolve(stdout);
    });
  });
}
