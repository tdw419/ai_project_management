/**
 * BaseDataSource: Interface for all pxOS dashboard data providers.
 */
class BaseDataSource {
  constructor(ctx, options = {}) {
    this.ctx = ctx;
    this.options = options;
    this.data = {
      projects: [],
      logs: [],
      issues: [],
      lastSync: null
    };
  }

  async initialize() {
    throw new Error('DataSource must implement initialize()');
  }

  async poll() {
    throw new Error('DataSource must implement poll()');
  }

  getData() {
    return this.data;
  }

  stop() {
    // Cleanup logic
  }
}

module.exports = BaseDataSource;
