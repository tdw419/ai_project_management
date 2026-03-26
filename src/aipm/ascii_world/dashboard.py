"""
ASCII World Dashboard - Visual shell for AIPM

Generates ASCII dashboards and serves them via HTTP/WebSocket.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import hashlib


@dataclass
class DashboardConfig:
    """Configuration for the dashboard"""
    title: str = "AIPM Dashboard"
    refresh_interval: int = 5
    max_items: int = 20
    show_hashes: bool = True


class ASCIIRenderer:
    """Renders data as ASCII art"""
    
    @staticmethod
    def box(title: str, content: List[str], width: int = 60) -> List[str]:
        """Create a bordered box with title"""
        lines = []
        lines.append("┌" + "─" * (width - 2) + "┐")
        
        # Title
        title_line = f"│ {title}"
        title_line += " " * (width - len(title_line) - 1) + "│"
        lines.append(title_line)
        lines.append("├" + "─" * (width - 2) + "┤")
        
        # Content
        for line in content:
            if len(line) > width - 4:
                line = line[:width - 7] + "..."
            padded = f"│ {line}"
            padded += " " * (width - len(padded) - 1) + "│"
            lines.append(padded)
        
        lines.append("└" + "─" * (width - 2) + "┘")
        return lines
    
    @staticmethod
    def progress_bar(percentage: float, width: int = 20) -> str:
        """Create a progress bar"""
        filled = int(percentage / 100 * width)
        return "█" * filled + "░" * (width - filled)
    
    @staticmethod
    def table(headers: List[str], rows: List[List[str]], col_widths: Optional[List[int]] = None) -> List[str]:
        """Create a table"""
        if not col_widths:
            col_widths = [max(len(row[i]) if i < len(row) else 0 for row in [headers] + rows) + 2
                         for i in range(len(headers))]
        
        lines = []
        
        # Header separator
        sep = "┌" + "┬".join("─" * w for w in col_widths) + "┐"
        lines.append(sep)
        
        # Headers
        header_cells = [h.ljust(w) for h, w in zip(headers, col_widths)]
        lines.append("│" + "│".join(header_cells) + "│")
        
        # Header/body separator
        sep = "├" + "┼".join("─" * w for w in col_widths) + "┤"
        lines.append(sep)
        
        # Rows
        for row in rows:
            cells = [(row[i] if i < len(row) else "").ljust(w) 
                    for i, w in enumerate(col_widths)]
            lines.append("│" + "│".join(cells) + "│")
        
        # Footer
        sep = "└" + "┴".join("─" * w for w in col_widths) + "┘"
        lines.append(sep)
        
        return lines


class Dashboard:
    """
    ASCII World Dashboard for AIPM.
    
    Generates visual dashboards and serves them.
    """
    
    def __init__(self, config: Optional[DashboardConfig] = None):
        self.config = config or DashboardConfig()
        self.renderer = ASCIIRenderer()
        self.ascii_path = Path.home() / ".aipm" / "ascii"
        self.ascii_path.mkdir(parents=True, exist_ok=True)
        self._data_providers: Dict[str, Callable] = {}
    
    def register_provider(self, name: str, provider: Callable) -> None:
        """Register a data provider"""
        self._data_providers[name] = provider
    
    def render(self) -> str:
        """Render the full dashboard"""
        lines = []
        
        # Header
        lines.extend([
            "╔════════════════════════════════════════════════════════════════════════╗",
            f"║  {self.config.title:<70}║",
            f"║  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<58}║",
            "╚════════════════════════════════════════════════════════════════════════╝",
            "",
        ])
        
        # System Status
        lines.extend(self._render_system_status())
        lines.append("")
        
        # Prompt Queue
        lines.extend(self._render_prompt_queue())
        lines.append("")
        
        # Projects
        lines.extend(self._render_projects())
        lines.append("")
        
        # Recent Activity
        lines.extend(self._render_activity())
        
        # Hash for verification
        content = "\n".join(lines)
        if self.config.show_hashes:
            hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
            lines.append("")
            lines.append(f"Hash: {hash_value}")
        
        return "\n".join(lines)
    
    def _render_system_status(self) -> List[str]:
        """Render system status section"""
        # Get data from providers or use defaults
        stats = self._data_providers.get("stats", lambda: {})()
        
        content = [
            f"Queue: {stats.get('pending', 0)} pending | {stats.get('completed_today', 0)} completed today",
            f"Total: {stats.get('total', 0)} prompts | Avg confidence: {stats.get('avg_confidence', 0):.2f}",
        ]
        
        return self.renderer.box("SYSTEM STATUS", content)
    
    def _render_prompt_queue(self) -> List[str]:
        """Render prompt queue section"""
        prompts = self._data_providers.get("prompts", lambda: [])()
        
        content = []
        for i, prompt in enumerate(prompts[:10]):
            score = prompt.get("score", 0)
            text = prompt.get("text", "")[:40]
            priority = prompt.get("priority", "?")
            content.append(f"{i+1}. [{score:.2f}] P{priority} - {text}...")
        
        if not content:
            content = ["No prompts in queue"]
        
        return self.renderer.box("PROMPT QUEUE (Top 10)", content)
    
    def _render_projects(self) -> List[str]:
        """Render projects section"""
        projects = self._data_providers.get("projects", lambda: [])()
        
        content = []
        for project in projects[:5]:
            name = project.get("name", "Unknown")
            completion = project.get("completion", 0)
            bar = self.renderer.progress_bar(completion)
            content.append(f"{name}: [{bar}] {completion:.0f}%")
        
        if not content:
            content = ["No projects yet"]
        
        return self.renderer.box("PROJECTS", content)
    
    def _render_activity(self) -> List[str]:
        """Render recent activity section"""
        activity = self._data_providers.get("activity", lambda: [])()
        
        content = []
        for event in activity[:10]:
            time = event.get("time", "?")
            msg = event.get("message", "")[:45]
            content.append(f"{time}: {msg}")
        
        if not content:
            content = ["No recent activity"]
        
        return self.renderer.box("RECENT ACTIVITY", content)
    
    def save(self, filename: str = "dashboard.ascii") -> Path:
        """Save dashboard to file"""
        path = self.ascii_path / filename
        path.write_text(self.render())
        return path
    
    async def serve(self, port: int = 8080) -> None:
        """Serve the dashboard via HTTP"""
        from aiohttp import web
        
        app = web.Application()
        
        async def handle_dashboard(request):
            return web.Response(text=self.render(), content_type="text/plain")
        
        async def handle_json(request):
            return web.json_response({
                "dashboard": self.render(),
                "updated": datetime.now().isoformat(),
            })
        
        app.router.add_get("/", handle_dashboard)
        app.router.add_get("/api/dashboard", handle_json)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", port)
        await site.start()
        
        print(f"Dashboard serving at http://localhost:{port}")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)


class HTMLDashboard:
    """HTML version of the dashboard with real-time updates"""
    
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AIPM Control Center</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'SF Mono', 'Consolas', monospace;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 {
            text-align: center;
            color: #00d9ff;
            margin-bottom: 20px;
            text-shadow: 0 0 10px rgba(0,217,255,0.5);
        }
        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
        .panel {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }
        .panel h2 {
            color: #00d9ff;
            border-bottom: 1px solid rgba(0,217,255,0.3);
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .stat { display: flex; justify-content: space-between; padding: 8px 0; }
        .stat-label { color: #888; }
        .stat-value { color: #fff; font-weight: bold; }
        .progress-bar {
            background: rgba(255,255,255,0.1);
            border-radius: 5px;
            overflow: hidden;
            height: 20px;
            margin: 10px 0;
        }
        .progress-fill {
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            height: 100%;
            transition: width 0.5s ease;
        }
        .prompt-item {
            padding: 10px;
            margin: 5px 0;
            background: rgba(255,255,255,0.03);
            border-radius: 5px;
            border-left: 3px solid #00d9ff;
        }
        .score { color: #00ff88; font-weight: bold; }
        .controls {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        button {
            background: linear-gradient(135deg, #00d9ff, #00ff88);
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            color: #1a1a2e;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover { transform: scale(1.05); }
        .hash {
            text-align: center;
            color: #666;
            font-size: 12px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 AIPM Control Center</h1>
        
        <div class="grid">
            <div class="panel">
                <h2>📊 System Status</h2>
                <div class="stat">
                    <span class="stat-label">Pending Prompts</span>
                    <span class="stat-value" id="pending">0</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Completed Today</span>
                    <span class="stat-value" id="completed">0</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Total Prompts</span>
                    <span class="stat-value" id="total">0</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Avg Confidence</span>
                    <span class="stat-value" id="confidence">0%</span>
                </div>
            </div>
            
            <div class="panel">
                <h2>📁 Projects</h2>
                <div id="projects">
                    <p>No projects yet</p>
                </div>
            </div>
            
            <div class="panel" style="grid-column: span 2;">
                <h2>📋 Prompt Queue</h2>
                <div id="prompts">
                    <p>No prompts in queue</p>
                </div>
                <div class="controls">
                    <button onclick="startLoop()">▶ Start</button>
                    <button onclick="pauseLoop()">⏸ Pause</button>
                    <button onclick="runOnce()">🔄 Run Once</button>
                    <button onclick="refresh()">🔃 Refresh</button>
                </div>
            </div>
        </div>
        
        <div class="hash" id="hash">
            Hash: loading...
        </div>
    </div>
    
    <script>
        let ws = null;
        
        function connect() {
            ws = new WebSocket('ws://localhost:' + window.location.port + '/ws');
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };
            ws.onclose = () => setTimeout(connect, 3000);
        }
        
        function updateDashboard(data) {
            if (data.stats) {
                document.getElementById('pending').textContent = data.stats.pending || 0;
                document.getElementById('completed').textContent = data.stats.completed_today || 0;
                document.getElementById('total').textContent = data.stats.total || 0;
                document.getElementById('confidence').textContent = 
                    ((data.stats.avg_confidence || 0) * 100).toFixed(0) + '%';
            }
            
            if (data.prompts) {
                const container = document.getElementById('prompts');
                container.innerHTML = data.prompts.map((p, i) => `
                    <div class="prompt-item">
                        <span class="score">[${p.score?.toFixed(2) || '?'}]</span>
                        P${p.priority || '?'} - ${p.text?.substring(0, 50) || ''}...
                    </div>
                `).join('');
            }
            
            if (data.hash) {
                document.getElementById('hash').textContent = 'Hash: ' + data.hash;
            }
        }
        
        function refresh() {
            fetch('/api/stats').then(r => r.json()).then(data => {
                updateDashboard(data);
            });
        }
        
        function startLoop() {
            fetch('/api/control', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'start'})
            });
        }
        
        function pauseLoop() {
            fetch('/api/control', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'pause'})
            });
        }
        
        function runOnce() {
            fetch('/api/control', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'run_once'})
            });
        }
        
        connect();
        refresh();
        setInterval(refresh, 5000);
    </script>
</body>
</html>
"""
    
    def __init__(self, dashboard: Dashboard):
        self.dashboard = dashboard
    
    def render(self) -> str:
        return self.HTML_TEMPLATE
