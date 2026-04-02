#!/usr/bin/env node
/**
 * PXOS CLI: Universal entry point for PXOS tools.
 */
const { Command } = require('commander');
const path = require('path');
const DashboardEngine = require('../aipm/core/dashboard_engine');
const DashboardRenderer = require('../aipm/core/dashboard_renderer');
const AIPMSQLiteSource = require('../aipm/core/data_sources/aipm_sqlite');
const SSHPublisher = require('../aipm/publishers/ssh_server');
const HTTPPublisher = require('../aipm/publishers/http_server');
const { VCCTextureBridge } = require('../aipm/core/vcc_texture_bridge');

const program = new Command();

program
  .name('pxos')
  .description('Pixel Operating System Tools')
  .version('1.0.0');

program
  .command('dashboard')
  .description('Launch the autonomous agent dashboard')
  .option('-s, --ssh-port <port>', 'SSH port', '2222')
  .option('-w, --web-port <port>', 'Web port', '8080')
  .option('-d, --db <path>', 'SQLite DB path', path.resolve(process.cwd(), 'data/truths.db'))
  .action(async (options) => {
    const sshPort = parseInt(options.sshPort);
    const webPort = parseInt(options.webPort);
    const dbPath = path.resolve(process.cwd(), options.db);

    console.log('--- STARTING PXOS DASHBOARD ---');

    // 1. Engine + Renderer
    const engine = new DashboardEngine();
    await engine.initialize();

    const renderer = new DashboardRenderer(engine);
    engine.renderDashboard = (links) => renderer.render(links);
    engine.renderDetail = (data) => renderer.renderDetail(data);

    // 2. VCC Bridge (for GlyphLang GPU VM visualization)
    const vccBridge = new VCCTextureBridge({ pollInterval: 100 });

    // 3. Publishers (start before data source so broadcast targets exist)
    const ssh = new SSHPublisher(engine.ctx, { cms: engine, port: sshPort });
    const http = new HTTPPublisher(engine.ctx, { cms: engine, port: webPort, vccBridge });

    await ssh.initialize();
    await http.initialize();
    await ssh.start();
    await http.start();

    // 3. Event listener (wire before source init so first sync isn't lost)
    engine.ctx.on('bridge:sync_complete', (data) => {
      engine.setBridgeData(data);
      ssh.broadcast();
      http.broadcast();
    });

    // 4. Data source (triggers initial sync immediately)
    const source = new AIPMSQLiteSource(engine.ctx, { dbPath });
    await source.initialize();

    console.log(`PXOS Dashboard is live.`);
    console.log(`  SSH: ssh -p ${sshPort} localhost`);
    console.log(`  Web: http://localhost:${webPort}`);

    process.on('SIGINT', () => {
      console.log('\nShutting down...');
      source.stop();
      vccBridge.stop();
      ssh.stop();
      http.stop();
      process.exit(0);
    });
  });

program.parse();
