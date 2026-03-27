"""
AIPM ASCII World - Sync Server

WebSocket server for real-time dashboard updates.
"""

import asyncio
import json
from pathlib import Path
from typing import Set, Optional
from aiohttp import web
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncServer:
    """
    WebSocket sync server for ASCII World dashboards.
    
    Broadcasts changes to all connected HTML clients.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[web.WebSocketResponse] = set()
        self.workspace = Path.home() / ".openclaw" / "workspace" / ".aipm"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.app = web.Application()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup HTTP and WebSocket routes."""
        self.app.router.add_get("/ws", self.websocket_handler)
        self.app.router.add_get("/dashboard/{name}", self.get_dashboard)
        self.app.router.add_post("/update/{name}", self.update_dashboard)
        self.app.router.add_get("/health", self.health_check)
    
    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.clients.add(ws)
        logger.info(f"Client connected. Total: {len(self.clients)}")
        
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self.handle_message(ws, data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        finally:
            self.clients.discard(ws)
            logger.info(f"Client disconnected. Total: {len(self.clients)}")
        
        return ws
    
    async def handle_message(self, ws: web.WebSocketResponse, data: dict):
        """Handle incoming WebSocket message."""
        action = data.get("action")
        
        if action == "ping":
            await ws.send_json({"action": "pong"})
        elif action == "subscribe":
            # Client wants to subscribe to updates
            await ws.send_json({"action": "subscribed", "status": "ok"})
        else:
            logger.warning(f"Unknown action: {action}")
    
    async def get_dashboard(self, request: web.Request) -> web.Response:
        """Get dashboard content."""
        name = request.match_info["name"]
        path = self.workspace / f"{name}.ascii"
        
        if not path.exists():
            return web.json_response({"error": "Dashboard not found"}, status=404)
        
        with open(path) as f:
            content = f.read()
        
        return web.json_response({"content": content})
    
    async def update_dashboard(self, request: web.Request) -> web.Response:
        """Update dashboard content and broadcast."""
        name = request.match_info["name"]
        data = await request.json()
        content = data.get("content", "")
        
        # Save to file
        path = self.workspace / f"{name}.ascii"
        with open(path, "w") as f:
            f.write(content)
        
        # Broadcast to all clients
        await self.broadcast({
            "action": "update",
            "dashboard": name,
            "content": content
        })
        
        return web.json_response({"status": "ok"})
    
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "clients": len(self.clients),
            "host": self.host,
            "port": self.port
        })
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.clients:
            return
        
        data = json.dumps(message)
        tasks = [client.send_str(data) for client in self.clients]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def run(self):
        """Run the server."""
        web.run_app(self.app, host=self.host, port=self.port)
    
    async def start(self):
        """Start server asynchronously."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"Sync server running at http://{self.host}:{self.port}")
        return runner


__all__ = ["SyncServer"]
