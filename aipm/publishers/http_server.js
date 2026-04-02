/**
 * HTTP and WebSocket Publisher for AIPM Dashboard.
 * Dracula-themed, interactive SPA over WebSocket.
 * Compliant with CONTRACTS.md.
 */
const http = require('http');
const { WebSocketServer } = require('ws');
const { handleCommand: loopControl } = require('./loop_control');
const { VCCTextureBridge, VCC_SIZE } = require('../core/vcc_texture_bridge');

// ANSI -> HTML (Dracula palette)
const ANSI_MAP = [
  [/\x1b\[0m/g, '</span>'],
  [/\x1b\[30m/g, '<span style="color:#6272a4">'],
  [/\x1b\[31m/g, '<span style="color:#ff5555">'],
  [/\x1b\[32m/g, '<span style="color:#50fa7b">'],
  [/\x1b\[33m/g, '<span style="color:#f1fa8c">'],
  [/\x1b\[34m/g, '<span style="color:#bd93f9">'],
  [/\x1b\[35m/g, '<span style="color:#ff79c6">'],
  [/\x1b\[36m/g, '<span style="color:#8be9fd">'],
  [/\x1b\[37m/g, '<span style="color:#f8f8f2">'],
  [/\x1b\[1m/g, '<span style="font-weight:bold">'],
  [/\x1b\[4m/g, '<span style="text-decoration:underline">'],
  [/\x1b\[[0-9;]*m/g, ''],
];

function ansiToHtml(text) {
  let h = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  for (const [re, rep] of ANSI_MAP) h = h.replace(re, rep);
  return h;
}

function getPage() {
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AIPM Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #282a36;
    color: #f8f8f2;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 14px;
    line-height: 1.45;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  #container {
    flex: 1;
    overflow-y: auto;
    border: 1px solid #44475a;
    padding: 12px;
    border-radius: 4px;
  }
  #dashboard {
    white-space: pre;
    tab-size: 4;
  }
  #input-bar {
    margin-top: 12px;
    display: flex;
    align-items: center;
    padding: 8px 12px;
    background: #1e1f29;
    border: 1px solid #44475a;
    border-radius: 4px;
  }
  #prompt { color: #bd93f9; margin-right: 10px; font-weight: bold; }
  #cmd {
    flex: 1;
    background: transparent;
    border: none;
    color: #50fa7b;
    font-family: inherit;
    font-size: 15px;
    outline: none;
  }
  #cmd::placeholder { color: #6272a4; }
  #status {
    position: fixed;
    top: 10px;
    right: 20px;
    font-size: 12px;
    color: #6c7086;
  }
  #status.connected { color: #50fa7b; }
  #status.disconnected { color: #ff5555; }
  .ctrl-msg { background: #282a36; color: #f1fa8c; padding: 8px 12px; margin: 4px 0; border-left: 3px solid #f1fa8c; font-family: monospace; }
</style>
</head>
<body>
<div id="status">connecting...</div>
<div id="container"><div id="dashboard">Loading AIPM Dashboard...</div></div>
<div id="input-bar">
  <span id="prompt">&gt;</span>
  <input type="text" id="cmd" autofocus spellcheck="false" autocomplete="off"
         placeholder="navigate [1-N] [b]ack [r]efresh | loop: pause/resume/inject <N>/status">
</div>
<script>
const el = document.getElementById('dashboard');
const statusEl = document.getElementById('status');
const cmd = document.getElementById('cmd');

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(proto + '//' + location.host + '/ws');

  ws.onopen = () => {
    statusEl.textContent = 'live';
    statusEl.className = 'connected';
  };

  ws.onmessage = (evt) => {
    el.innerHTML = evt.data;
  };

  ws.onclose = () => {
    statusEl.textContent = 'reconnecting...';
    statusEl.className = 'disconnected';
    setTimeout(connect, 3000);
  };

  document.onkeydown = (e) => {
    if (document.activeElement === cmd) return;
    if (e.key === 'b' || e.key === 'r') {
      ws.send(JSON.stringify({ type: 'input', value: e.key }));
    } else if (/[1-9]/.test(e.key)) {
      ws.send(JSON.stringify({ type: 'input', value: e.key }));
    } else if (e.key === '0') {
      cmd.focus();
    }
  };

  cmd.onkeydown = (e) => {
    if (e.key === 'Enter') {
      const val = cmd.value.trim();
      if (val) {
        ws.send(JSON.stringify({ type: 'input', value: val }));
        cmd.value = '';
      }
    }
  };
}

document.addEventListener('click', () => cmd.focus());
connect();
</script>
</body>
</html>`;
}

class HTTPPublisher {
  constructor(ctx, options = {}) {
    this.ctx = ctx;
    this.cms = options.cms;
    this.port = options.port || 8080;
    this.host = options.host || '0.0.0.0';
    this.httpServer = null;
    this.wss = null;
    this.clients = new Map(); // ws -> { view, route, linkData, history }
    this.vccBridge = options.vccBridge || null;
  }

  async initialize() {
    const page = getPage();

    if (this.vccBridge) {
      this.vccBridge.start();
    }

    this.httpServer = http.createServer((req, res) => {
      if (req.url === '/' || req.url === '/index.html') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(page);
      } else if (req.url === '/health') {
        const data = this.cms.bridgeData;
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
      } else if (req.url === '/api/v1/vcc/texture') {
        const rgba = this.vccBridge?.getRawRGBA();
        if (rgba) {
          res.writeHead(200, {
            'Content-Type': 'application/octet-stream',
            'X-VCC-Width': VCC_SIZE,
            'X-VCC-Height': VCC_SIZE
          });
          res.end(rgba);
        } else {
          res.writeHead(404);
          res.end('VCC not available');
        }
      } else if (req.url === '/api/v1/vcc/ascii') {
        const ascii = this.vccBridge?.toASCII(80, 24) || 'VCC bridge not initialized';
        res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end(ascii);
      } else if (req.url === '/api/v1/vcc/stats') {
        const stats = this.vccBridge?.getLatestStats() || { activeVMs: 0, fillPct: 0, avgBrightness: 0 };
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(stats));
      } else {
        res.writeHead(404);
        res.end('Not found');
      }
    });

    this.wss = new WebSocketServer({ server: this.httpServer, path: '/ws' });

    if (this.vccBridge) {
      this.vccBridge.onFrame = (data) => {
        const msg = JSON.stringify({ type: 'vcc-frame', stats: data.stats });
        for (const [ws, state] of this.clients) {
          try { ws.send(msg); } catch (e) { this.clients.delete(ws); }
        }
      };
    }

    this.wss.on('connection', (ws) => {
      this.clients.set(ws, { view: 'dashboard', route: null, linkData: null, history: [] });
      try { ws.send(this.renderFrame(this.clients.get(ws))); } catch (e) {}

      ws.on('message', (raw) => {
        try {
          const msg = JSON.parse(raw.toString());
          if (msg.type === 'input') {
            this.handleInput(ws, msg.value);
          }
        } catch (e) {}
      });

      ws.on('close', () => this.clients.delete(ws));
      ws.on('error', () => this.clients.delete(ws));
    });
  }

  buildLinkTable() {
    const links = new Map();
    const data = this.cms.bridgeData;
    let idx = 1;
    if (data.projects) {
      for (const p of data.projects) {
        links.set(idx, { route: `/projects/${p.data?.name || '?'}`, type: 'project', data: p });
        idx++;
      }
    }
    if (data.issues) {
      for (const issue of data.issues) {
        links.set(idx, { route: `/issues/${issue.data?.number || '?'}`, type: 'issue', data: issue });
        idx++;
      }
    }
    return links;
  }

  handleInput(ws, input) {
    const state = this.clients.get(ws);
    if (!state) return;

    if (input === 'q' || input === 'quit') {
      ws.close();
      return;
    }

    if (input === 'r') {
      try { ws.send(this.renderFrame(state)); } catch (e) {}
      return;
    }

    if (input === 'b') {
      if (state.history.length > 0) {
        const prev = state.history.pop();
        Object.assign(state, prev);
      } else {
        Object.assign(state, { view: 'dashboard', route: null, linkData: null });
      }
      try { ws.send(this.renderFrame(state)); } catch (e) {}
      return;
    }

    const num = parseInt(input, 10);
    if (!isNaN(num)) {
      const links = this.buildLinkTable();
      const link = links.get(num);
      if (link) {
        state.history.push({ view: state.view, route: state.route, linkData: state.linkData });
        Object.assign(state, { view: 'detail', route: link.route, linkData: link });
        try { ws.send(this.renderFrame(state)); } catch (e) {}
      }
      return;
    }

    // Loop control commands
    const ctrlResult = loopControl(input);
    if (ctrlResult) {
      // Strip ANSI codes for HTML display, wrap in a highlight div
      const clean = ctrlResult.replace(/\x1b\[[0-9;]*m/g, '');
      try { ws.send('<div class="ctrl-msg">' + clean + '</div>'); } catch (e) {}
      return;
    }
  }

  renderFrame(state) {
    if (state && state.view === 'detail' && state.linkData) {
      return ansiToHtml(this.cms.renderDetail(state.linkData));
    }
    return ansiToHtml(this.cms.renderDashboard(this.buildLinkTable()));
  }

  async start() {
    return new Promise((resolve, reject) => {
      this.httpServer.listen(this.port, this.host, () => {
        console.log(`LOG: [HTTP_PUBLISHER] Web dashboard at http://localhost:${this.port}`);
        resolve();
      });
    });
  }

  broadcast() {
    for (const [ws, state] of this.clients) {
      try {
        if (state.view === 'dashboard') {
          ws.send(this.renderFrame(state));
        }
      } catch (e) {
        this.clients.delete(ws);
      }
    }
  }

  stop() {
    if (this.vccBridge) {
      this.vccBridge.stop();
    }
    for (const ws of this.clients.keys()) { try { ws.close(); } catch (e) {} }
    this.httpServer?.close();
  }
}

module.exports = HTTPPublisher;
