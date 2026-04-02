#!/usr/bin/env node
import { Command } from 'commander';
import { Scheduler } from '../src/core/scheduler.js';
import { readFile } from 'fs/promises';
import { resolve } from 'path';
import YAML from 'yaml';
import type { AipmConfig, ProjectConfig } from '../src/models/config.js';
import { mkdir } from 'fs/promises';

const program = new Command();

program
  .name('openspec-aipm')
  .description('Autonomous AI project manager built on OpenSpec')
  .version('3.0.0-alpha.1');

program
  .command('run')
  .description('Run the AIPM loop')
  .option('-c, --config <path>', 'Path to config file', 'aipm.yaml')
  .option('-i, --interval <seconds>', 'Cycle interval', '60')
  .action(async (opts) => {
    const configPath = resolve(opts.config);
    const config = await loadConfig(configPath);
    config.intervalSeconds = parseInt(opts.interval) || config.intervalSeconds;

    const scheduler = new Scheduler(config);

    process.on('SIGINT', () => {
      console.log('\nShutting down...');
      scheduler.stop();
    });
    process.on('SIGTERM', () => {
      scheduler.stop();
    });

    await scheduler.runForever();
  });

program
  .command('once')
  .description('Run a single cycle')
  .option('-c, --config <path>', 'Path to config file', 'aipm.yaml')
  .action(async (opts) => {
    const configPath = resolve(opts.config);
    const config = await loadConfig(configPath);
    const scheduler = new Scheduler(config);
    await scheduler.runOnce();
  });

program
  .command('status')
  .description('Show status of all managed projects')
  .option('-c, --config <path>', 'Path to config file', 'aipm.yaml')
  .action(async (opts) => {
    const configPath = resolve(opts.config);
    const config = await loadConfig(configPath);
    const bridge = new (await import('../src/core/openspec-bridge.js')).OpenSpecBridge(config.openspecBin);

    for (const project of config.projects) {
      const changes = await bridge.listChanges(project.path);
      const active = changes.filter(c => c.status !== 'complete');
      const total = changes.length;

      console.log(
        `${project.name}: ${total} changes, ${active.length} active`
      );
      for (const change of active.slice(0, 5)) {
        console.log(
          `  ${change.name}: ${change.completedTasks}/${change.totalTasks} tasks (${change.status})`
        );
      }
    }
  });

// ── Output Management Commands ──

program
  .command('mine')
  .description('Mine hermes session history for insights')
  .option('-l, --limit <n>', 'Max sessions to analyze', '50')
  .option('--category <cat>', 'Filter: productive, no_action, api_failure, all', 'all')
  .option('--project <name>', 'Filter by project name')
  .option('--stats', 'Show aggregate stats only')
  .action(async (opts) => {
    const { SessionMiner } = await import('../src/core/output-management/session-miner.js');
    const miner = new SessionMiner();

    try {
      if (opts.stats) {
        const stats = miner.getStats();
        console.log(`Sessions: ${stats.totalSessions}`);
        console.log(`  Productive: ${stats.productive}`);
        console.log(`  No action:  ${stats.noAction}`);
        console.log(`  API fails:  ${stats.apiFailures}`);
        console.log(`Tokens: ${stats.totalTokensUsed.toLocaleString()} total, ${stats.wastedTokens.toLocaleString()} wasted (${(stats.wastedTokens / stats.totalTokensUsed * 100).toFixed(1)}%)`);
        return;
      }

      const cat = opts.category === 'all' ? undefined : opts.category;
      const sessions = miner.mineSessions({
        limit: parseInt(opts.limit),
        category: cat as any,
      });

      for (const s of sessions) {
        const tags: string[] = [];
        if (s.prompt?.project) tags.push(s.prompt.project);
        if (s.prompt?.changeName) tags.push(s.prompt.changeName);
        if (s.prompt?.sectionId) tags.push(`SEC-${s.prompt.sectionId}`);
        tags.push(`${s.messageCount}msg/${s.toolCallCount}tools`);
        tags.push(`${s.totalTokens.toLocaleString()}tok`);

        console.log(`[${s.category}] ${s.id.slice(0, 20)}  ${tags.join(' | ')}`);

        if (s.outcome?.summary) {
          const firstLine = s.outcome.summary.split('\n')[0]?.slice(0, 120);
          console.log(`  -> ${firstLine}`);
        }

        if (s.outcome?.testCountMentions.length) {
          console.log(`  tests: ${s.outcome.testCountMentions.join(', ')}`);
        }
      }
    } finally {
      miner.close();
    }
  });

program
  .command('correlate')
  .description('Correlate hermes sessions with AIPM outcomes')
  .option('--project <name>', 'Filter by project')
  .option('--waste', 'Show token waste analysis')
  .action(async (opts) => {
    const { OutcomeCorrelator } = await import('../src/core/output-management/outcome-correlator.js');
    const correlator = new OutcomeCorrelator();

    try {
      if (opts.waste) {
        const waste = correlator.findTokenWaste();
        console.log('Top token waste:');
        let total = 0;
        for (const w of waste) {
          total += w.tokens;
          console.log(`  ${w.sessionId.slice(0, 20)}  ${w.tokens.toLocaleString()} tok  ${w.category}: ${w.reason}`);
        }
        console.log(`Total wasted: ${total.toLocaleString()} tokens`);
        return;
      }

      if (opts.project) {
        const metrics = correlator.getProjectMetrics(opts.project);
        console.log(`Project: ${metrics.project}`);
        console.log(`  Attempts:  ${metrics.totalAttempts}`);
        console.log(`  Success:   ${(metrics.successRate * 100).toFixed(1)}%`);
        console.log(`  Avg delta: ${metrics.avgTestDelta.toFixed(1)} tests`);
        console.log(`  Avg files: ${metrics.avgFilesChanged.toFixed(1)}`);
        console.log(`  Tokens:    ${metrics.totalTokens.toLocaleString()} (${metrics.wastedTokens.toLocaleString()} wasted)`);

        if (metrics.topPatterns.length > 0) {
          console.log(`  Top patterns:`);
          for (const p of metrics.topPatterns) {
            console.log(`    ${p.pattern}: ${p.count}x, ${(p.successRate * 100).toFixed(0)}% success`);
          }
        }
        return;
      }

      // All projects
      const allMetrics = correlator.getAllProjectMetrics();
      for (const m of allMetrics) {
        console.log(
          `${m.project}: ${m.totalAttempts} attempts, ` +
          `${(m.successRate * 100).toFixed(0)}% success, ` +
          `avg delta ${m.avgTestDelta.toFixed(1)}`
        );
      }
    } finally {
      correlator.close();
    }
  });

program
  .command('learnings')
  .description('Extract and manage learnings from agent sessions')
  .option('--project <name>', 'Project to extract learnings for')
  .option('--mine', 'Mine new learnings from recent sessions')
  .option('--show', 'Show current learnings')
  .action(async (opts) => {
    const { SessionMiner } = await import('../src/core/output-management/session-miner.js');
    const { LearningsExtractor } = await import('../src/core/output-management/learnings-extractor.js');

    const extractor = new LearningsExtractor('/tmp/openspec_aipm/learnings');

    if (opts.mine) {
      const miner = new SessionMiner();
      try {
        const sessions = miner.mineSessions({ limit: 200 });
        const productive = sessions.filter(s => s.category === 'productive');
        console.log(`Mining ${productive.length} productive sessions...`);

        const learnings = extractor.extractFromSessions(productive);
        console.log(`Extracted ${learnings.length} learnings`);

        if (opts.project) {
          const filtered = learnings.filter(l => l.project === opts.project);
          await extractor.saveLearnings(opts.project, filtered);
          console.log(`Saved ${filtered.length} learnings for ${opts.project}`);
        } else {
          // Save all by project
          const byProject = new Map<string, typeof learnings>();
          for (const l of learnings) {
            if (!byProject.has(l.project)) byProject.set(l.project, []);
            byProject.get(l.project)!.push(l);
          }
          for (const [project, items] of byProject) {
            await extractor.saveLearnings(project, items);
            console.log(`  ${project}: ${items.length} learnings`);
          }
        }
      } finally {
        miner.close();
      }
      return;
    }

    if (opts.show && opts.project) {
      const result = await extractor.loadLearnings(opts.project);
      console.log(result.summary);
      return;
    }

    console.log('Use --mine to extract learnings, --show --project <name> to view');
  });

program
  .command('search <query>')
  .description('Search hermes session history')
  .option('-l, --limit <n>', 'Max results', '10')
  .action(async (query, opts) => {
    const { SessionMiner } = await import('../src/core/output-management/session-miner.js');
    const miner = new SessionMiner();
    try {
      const results = miner.search(query, parseInt(opts.limit));
      for (const r of results) {
        console.log(`Session: ${r.sessionId.slice(0, 20)}`);
        console.log(`  ${r.snippet.slice(0, 150)}`);
        console.log();
      }
    } finally {
      miner.close();
    }
  });

program.parse();

async function loadConfig(path: string): Promise<AipmConfig> {
  const raw = await readFile(path, 'utf-8');
  const data = YAML.parse(raw);

  return {
    intervalSeconds: data.interval || 60,
    maxGlobalParallel: data.maxParallel || 4,
    cloudModel: data.cloudModel || 'glm-5.1',
    localModel: data.localModel || 'qwen3.5-tools',
    openspecBin: data.openspecBin,
    hermesBin: data.hermesBin,
    dataDir: data.dataDir || '/tmp/openspec_aipm',
    projects: (data.projects || []).map((p: any) => ({
      name: p.name,
      path: resolve(p.path),
      language: p.language || 'unknown',
      testCommand: p.testCommand || 'npm test',
      protectedFiles: p.protectedFiles || [],
      maxParallel: p.maxParallel || 1,
      specDriven: p.specDriven !== false,
    })),
  };
}
