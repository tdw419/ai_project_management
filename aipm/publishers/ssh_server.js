/**
 * SSH Publisher for AIPM Dashboard.
 * Interactive ASCII-SPA: numbered links, back stack, in-place re-render.
 */
const { Server } = require('ssh2');
const fs = require('fs');
const path = require('path');
const { handleCommand: loopControl } = require('./loop_control');

class SSHPublisher {
  constructor(ctx, options = {}) {
    this.ctx = ctx;
    this.cms = options.cms;
    this.port = options.port || 2222;
    this.host = options.host || '0.0.0.0';
    this.server = null;
    this.clients = new Set();
  }

  async initialize() {
    const keyPath = path.resolve(process.cwd(), '.ssh/id_rsa');
    if (!fs.existsSync(keyPath)) {
      fs.mkdirSync(path.dirname(keyPath), { recursive: true });
      const { execSync } = require('child_process');
      execSync(`ssh-keygen -t rsa -b 2048 -f ${keyPath} -N "" -q`);
    }

    this.server = new Server({
      hostKeys: [fs.readFileSync(keyPath)]
    }, (client) => {
      client.on('authentication', (ctx) => ctx.accept())
            .on('ready', () => {
        client.on('session', (accept) => {
          const session = accept();
          session.on('pty', (accept) => { if (accept) accept(); })
                 .on('shell', (accept) => {
            const stream = accept();
            this.clients.add(stream);
            this.handleStream(stream);
            stream.on('close', () => this.clients.delete(stream));
          });
        });
      }).on('end', () => {});
    });
  }

  async start() {
    return new Promise((resolve, reject) => {
      this.server.on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
          this.port++;
          this.server.listen(this.port, this.host);
        } else {
          reject(err);
        }
      });
      this.server.listen(this.port, this.host, () => {
        console.log(`LOG: [SSH_PUBLISHER] Dashboard available at ssh://${this.host}:${this.port}`);
        resolve();
      });
    });
  }

  /**
   * Build a link table from current bridgeData.
   * Returns Map<number, {route, label}>
   */
  buildLinkTable() {
    const links = new Map();
    const data = this.cms.bridgeData;
    let idx = 1;

    // Projects
    if (data.projects && data.projects.length > 0) {
      for (const p of data.projects) {
        const name = p.data?.name || '???';
        links.set(idx, {
          route: `/projects/${name}`,
          label: name,
          type: 'project',
          data: p,
        });
        idx++;
      }
    }

    // Issues
    if (data.issues && data.issues.length > 0) {
      for (const issue of data.issues) {
        const num = issue.data?.number || '?';
        const title = (issue.data?.title || '').substring(0, 40);
        links.set(idx, {
          route: `/issues/${num}`,
          label: `#${num} ${title}`,
          type: 'issue',
          data: issue,
        });
        idx++;
      }
    }

    return links;
  }

  async handleStream(stream) {
    // Navigation state per session
    const history = [];
    let currentView = 'dashboard'; // 'dashboard' | 'detail'
    let currentRoute = null;
    let currentLinkData = null;

    const render = () => {
      const links = this.buildLinkTable();
      stream.write('\x1b[2J\x1b[H'); // Clear screen, cursor home

      if (currentView === 'dashboard') {
        const frame = this.cms.renderDashboard(links);
        stream.write(frame);
      } else {
        stream.write(this.cms.renderDetail(currentLinkData));
      }

      // Command bar
      stream.write('\r\n');
      const nav = currentView === 'dashboard'
        ? '\x1b[1;36m[b]ack [r]efresh [q]uit [pause/resume/inject/status] | Select [1-N]\x1b[0m'
        : '\x1b[1;36m[b]ack [r]efresh [q]uit [pause/resume/inject/status]\x1b[0m';
      stream.write(nav);
      stream.write('\r\n> ');
    };

    // Initial render
    render();

    // Handle input
    stream.on('data', (data) => {
      const input = data.toString().trim();
      if (!input) return;

      if (input === 'q' || input === 'quit' || input === 'exit') {
        stream.write('\r\nGoodbye!\r\n');
        stream.end();
        return;
      }

      if (input === 'r') {
        render();
        return;
      }

      if (input === 'b') {
        if (history.length > 0) {
          const prev = history.pop();
          currentView = prev.view;
          currentRoute = prev.route;
          currentLinkData = prev.linkData;
        } else {
          currentView = 'dashboard';
          currentRoute = null;
          currentLinkData = null;
        }
        render();
        return;
      }

      // Loop control commands
      const ctrlResult = loopControl(input);
      if (ctrlResult) {
        stream.write(ctrlResult + '\r\n> ');
        return;
      }

      // Number input: resolve link
      const num = parseInt(input, 10);
      if (!isNaN(num)) {
        const links = this.buildLinkTable();
        const link = links.get(num);
        if (link) {
          // Push current state to history
          history.push({ view: currentView, route: currentRoute, linkData: currentLinkData });
          currentView = 'detail';
          currentRoute = link.route;
          currentLinkData = link;
          render();
        } else {
          stream.write(`\x1b[1;31mInvalid: ${num} (1-${links.size})\x1b[0m\r\n> `);
        }
      }
    });
  }

  /**
   * Push updated frame to all connected SSH clients (dashboard view only).
   */
  broadcast() {
    const frame = this.cms.renderDashboard();
    for (const stream of this.clients) {
      try {
        stream.write('\x1b[2J\x1b[H');
        stream.write(frame);
        stream.write('\r\n\x1b[1;36m[b]ack [r]efresh [q]uit | Select [1-N]\x1b[0m\r\n> ');
      } catch (e) {
        this.clients.delete(stream);
      }
    }
  }

  stop() {
    for (const s of this.clients) { try { s.end(); } catch (e) {} }
    this.server?.close();
  }
}

module.exports = SSHPublisher;
