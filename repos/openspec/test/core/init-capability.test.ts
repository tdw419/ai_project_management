/**
 * Tests for SEC-2: Capability-Aware Delivery Planning in init.
 *
 * Verifies per-tool command surface resolution during init:
 *  - delivery=commands + trae → skills retained/generated, no adapter error
 *  - mixed tools (claude,trae) with per-tool expected outputs
 *  - delivery=both with trae shows skills-invocable report
 *
 * Uses isolated XDG_CONFIG_HOME so global config changes don't leak
 * to other test files running in parallel.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { runCLI } from '../helpers/run-cli.js';
import type { Delivery } from '../../src/core/global-config.js';

const ISOLATED_CONFIG_DIR = path.join(os.tmpdir(), `openspec-sec2-xdg-${process.pid}`);

function makeTempDir(): string {
  return path.join(os.tmpdir(), `openspec-sec2-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
}

function writeIsolatedConfig(config: Record<string, unknown>): void {
  const dir = path.join(ISOLATED_CONFIG_DIR, 'openspec');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'config.json'), JSON.stringify(config, null, 2) + '\n', 'utf-8');
}

function removeIsolatedConfig(): void {
  fs.rmSync(ISOLATED_CONFIG_DIR, { recursive: true, force: true });
}

function getOutput(result: { stdout: string; stderr: string }): string {
  return (result.stdout + '\n' + result.stderr).replace(/\x1b\[[0-9;]*m/g, '');
}

describe('SEC-2: capability-aware init delivery', () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = makeTempDir();
    fs.mkdirSync(tempDir, { recursive: true });
    removeIsolatedConfig();
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
    removeIsolatedConfig();
  });

  describe('delivery=commands + trae (skills-invocable)', () => {
    beforeEach(() => {
      writeIsolatedConfig({ delivery: 'commands', profile: 'core', featureFlags: {} });
    });

    it('should generate skills for trae under delivery=commands', async () => {
      const result = await runCLI(['init', '--tools', 'trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });
      expect(result.exitCode).toBe(0);

      // Skills should exist (skills-invocable tool keeps skills under delivery=commands)
      const skillFile = path.join(tempDir, '.trae', 'skills', 'openspec-propose', 'SKILL.md');
      const stat = await fs.promises.stat(skillFile).catch(() => null);
      expect(stat).not.toBeNull();
      expect(stat!.isFile()).toBe(true);

      // Output should not say "no adapter"
      const output = getOutput(result);
      expect(output).not.toContain('no adapter');

      // Output should indicate skills used as command surface
      expect(output).toContain('Skills used as command surface');
    });

    it('should not remove existing skills for trae under delivery=commands', async () => {
      // First init to create skills
      await runCLI(['init', '--tools', 'trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });

      // Second init should not remove skills
      const result = await runCLI(['init', '--tools', 'trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });
      expect(result.exitCode).toBe(0);

      const skillFile = path.join(tempDir, '.trae', 'skills', 'openspec-propose', 'SKILL.md');
      const stat = await fs.promises.stat(skillFile).catch(() => null);
      expect(stat).not.toBeNull();
      expect(stat!.isFile()).toBe(true);
    });
  });

  describe('mixed tools (claude,trae) with per-tool outputs', () => {
    beforeEach(() => {
      writeIsolatedConfig({ delivery: 'commands', profile: 'core', featureFlags: {} });
    });

    it('should generate commands for claude and skills for trae', async () => {
      const result = await runCLI(['init', '--tools', 'claude,trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });
      expect(result.exitCode).toBe(0);

      // Claude: adapter-based commands should exist
      const claudeCommandFile = path.join(tempDir, '.claude', 'commands', 'opsx', 'explore.md');
      const claudeStat = await fs.promises.stat(claudeCommandFile).catch(() => null);
      expect(claudeStat).not.toBeNull();

      // Trae: skills should exist (not removed)
      const traeSkillFile = path.join(tempDir, '.trae', 'skills', 'openspec-propose', 'SKILL.md');
      const traeStat = await fs.promises.stat(traeSkillFile).catch(() => null);
      expect(traeStat).not.toBeNull();

      // Output should not say "no adapter" for trae
      const output = getOutput(result);
      expect(output).not.toContain('no adapter');
      expect(output).toContain('Skills used as command surface');
    });

    it('should remove claude skills but keep trae skills under delivery=commands', async () => {
      // First init with delivery=both to create everything
      writeIsolatedConfig({ delivery: 'both', profile: 'core', featureFlags: {} });
      await runCLI(['init', '--tools', 'claude,trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });

      // Verify claude skills exist
      const claudeSkillDir = path.join(tempDir, '.claude', 'skills', 'openspec-propose');
      expect(fs.existsSync(claudeSkillDir)).toBe(true);

      // Now switch to delivery=commands and re-init
      writeIsolatedConfig({ delivery: 'commands', profile: 'core', featureFlags: {} });
      const result = await runCLI(['init', '--tools', 'claude,trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });
      expect(result.exitCode).toBe(0);

      // Claude skills should be removed
      expect(fs.existsSync(claudeSkillDir)).toBe(false);

      // Trae skills should still exist
      const traeSkillFile = path.join(tempDir, '.trae', 'skills', 'openspec-propose', 'SKILL.md');
      const traeStat = await fs.promises.stat(traeSkillFile).catch(() => null);
      expect(traeStat).not.toBeNull();
    });
  });

  describe('delivery=both (default) with trae', () => {
    it('should generate both skills and commands for claude, skills-only for trae', async () => {
      // Use isolated config with no config file → defaults to delivery='both'
      const result = await runCLI(['init', '--tools', 'claude,trae', '--force'], {
        cwd: tempDir,
        env: { XDG_CONFIG_HOME: ISOLATED_CONFIG_DIR },
      });
      expect(result.exitCode).toBe(0);

      // Claude: both skills and commands
      const claudeSkillFile = path.join(tempDir, '.claude', 'skills', 'openspec-propose', 'SKILL.md');
      const claudeCmdFile = path.join(tempDir, '.claude', 'commands', 'opsx', 'explore.md');
      expect(fs.existsSync(claudeSkillFile)).toBe(true);
      expect(fs.existsSync(claudeCmdFile)).toBe(true);

      // Trae: skills exist, no adapter-based commands
      const traeSkillFile = path.join(tempDir, '.trae', 'skills', 'openspec-propose', 'SKILL.md');
      expect(fs.existsSync(traeSkillFile)).toBe(true);

      // Output should show skills-invocable
      const output = getOutput(result);
      expect(output).toContain('Skills used as command surface');
    });
  });
});
