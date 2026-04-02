/**
 * DashboardEngine: Focused, high-performance engine for the PXOS Dashboard.
 * Now self-contained using internalized vendor modules.
 */
const path = require('path');
const { EventEmitter } = require('events');

class DashboardEngine {
  constructor(config = {}) {
    this.config = Object.assign({
      root: process.cwd(),
      dashboard_layout: 'aipm-dashboard' // Name of preset in vendor/layout-presets
    }, config);
    
    this.modules = {};
    this.vendorPath = path.resolve(__dirname, 'vendor');
    this.bridgeData = { projects: [], logs: [], issues: [], lastSync: null };
    this.ctx = new EventEmitter();
    this.ctx.state = { is_initialized: false };
    this.ctx.getConfig = (key) => this.config[key];
  }

  async initialize() {
    const vp = this.vendorPath;

    // Load ONLY the essential modules from local vendor
    const [
      { EventBus },
      { ContentStore },
      { LayoutEngine }
    ] = await Promise.all([
      import(`file://${path.join(vp, 'event-bus.js')}`),
      import(`file://${path.join(vp, 'content-store.js')}`),
      import(`file://${path.join(vp, 'layout-engine.js')}`)
    ]);

    const eventBus = new EventBus();
    const contentStore = new ContentStore({
      filePath: `/tmp/pxos-dashboard-${Date.now()}.json`
    });
    const layoutEngine = new LayoutEngine({ width: 80, height: 24 });

    this.modules = { eventBus, contentStore, layoutEngine };

    // Wire event helpers onto ctx
    this.ctx.modules = this.modules;
    this.ctx.on = (ev, cb) => eventBus.on(ev, cb);
    this.ctx.emit = (ev, data) => eventBus.emit(ev, data);
    this.ctx.removeListener = (ev, cb) => eventBus.removeListener(ev, cb);

    this.ctx.state.is_initialized = true;
    console.log(`LOG: [ENGINE] Initialized PXOS dashboard engine (self-contained).`);
    return true;
  }

  setBridgeData(data) {
    this.bridgeData = data;
  }
}

module.exports = DashboardEngine;
