"""
API Server - REST and WebSocket API for AIPM

Provides HTTP endpoints and WebSocket for real-time updates.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web
import aiofiles

from aipm.core.engine import PromptSystem, Prompt
from aipm.project.manager import ProjectManager
from aipm.ascii_world.dashboard import Dashboard, HTMLDashboard
from aipm.api.health import handle_health, handle_ping
from aipm.loop_control import LoopController, LoopCommand


class APIServer:
    """
    REST + WebSocket API server for AIPM.
    
    Endpoints:
    - GET /api/prompts - Get next prompts
    - GET /api/stats - Get statistics
    - GET /api/completed - Recent completed prompts
    - POST /api/prompts - Add new prompt
    - GET /api/analyze/:id - Analyze a prompt
    - POST /api/control - Control actions
    - GET /api/health - System health check (Phase 1.2)
    - GET /ping - Simple heartbeat
    - WS /ws - Real-time updates
    """
    
    def __init__(
        self,
        system: Optional[PromptSystem] = None,
        pm: Optional[ProjectManager] = None,
        port: int = 8080,
    ):
        self.system = system or PromptSystem()
        self.pm = pm or ProjectManager()
        self.port = port
        self.dashboard = Dashboard()
        self.html_dashboard = HTMLDashboard(self.dashboard)
        self._running = False
        self._clients = set()
        self.loop_controller = LoopController()
    
    def create_app(self) -> web.Application:
        """Create the aiohttp application"""
        app = web.Application()
        
        # Routes
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/control_center.html", self.handle_html_dashboard)
        app.router.add_get("/api/health", handle_health)
        app.router.add_get("/ping", handle_ping)
        app.router.add_get("/api/prompts", self.handle_get_prompts)
        app.router.add_get("/api/stats", self.handle_get_stats)
        app.router.add_get("/api/completed", self.handle_get_completed)
        app.router.add_post("/api/prompts", self.handle_add_prompt)
        app.router.add_get("/api/analyze/{prompt_id}", self.handle_analyze)
        app.router.add_post("/api/control", self.handle_control)
        app.router.add_get("/api/status", self.handle_loop_status)
        app.router.add_get("/ws", self.handle_websocket)
        
        return app
    
    async def handle_index(self, request: web.Request) -> web.Response:
        """Serve ASCII dashboard"""
        return web.Response(text=self.dashboard.render(), content_type="text/plain")
    
    async def handle_html_dashboard(self, request: web.Request) -> web.Response:
        """Serve HTML dashboard"""
        return web.Response(text=self.html_dashboard.render(), content_type="text/html")
    
    async def handle_get_prompts(self, request: web.Request) -> web.Response:
        """Get pending prompts"""
        limit = int(request.query.get("limit", "10"))
        prompts = self.system.queue.get_pending(limit)
        
        # Score them
        scored = []
        for p in prompts:
            score = self.system.prioritizer.score(p)
            scored.append({
                "id": p.id,
                "text": p.text,
                "category": p.category.value,
                "priority": p.priority,
                "confidence": p.confidence,
                "score": score,
            })
        
        # Sort by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        return web.json_response({"prompts": scored})
    
    async def handle_get_stats(self, request: web.Request) -> web.Response:
        """Get system statistics"""
        stats = self.system.queue.get_stats()
        projects = self.pm.list_projects()
        
        project_data = []
        for p in projects:
            pstats = self.pm.get_project_stats(p.id)
            project_data.append({
                "id": p.id,
                "name": p.name,
                "completion": pstats["completion_percentage"],
            })
        
        return web.json_response({
            "stats": stats,
            "projects": project_data,
            "hash": datetime.now().isoformat(),
        })
    
    async def handle_get_completed(self, request: web.Request) -> web.Response:
        """Get recently completed prompts"""
        limit = int(request.query.get("limit", "20"))
        from aipm.core.engine import PromptStatus
        prompts = self.system.queue.get_by_status(PromptStatus.COMPLETED, limit)
        
        return web.json_response({
            "prompts": [p.to_dict() for p in prompts]
        })
    
    async def handle_add_prompt(self, request: web.Request) -> web.Response:
        """Add a new prompt"""
        data = await request.json()
        
        from aipm.core.engine import Prompt, PromptCategory
        
        prompt = Prompt(
            id=f"prompt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            text=data.get("text", ""),
            category=PromptCategory(data.get("category", "code_gen")),
            priority=data.get("priority", 5),
            confidence=data.get("confidence", 0.5),
        )
        
        self.system.add_prompt(prompt)
        
        # Broadcast update
        await self._broadcast({"type": "prompt_added", "prompt": prompt.to_dict()})
        
        return web.json_response({"status": "ok", "id": prompt.id})
    
    async def handle_analyze(self, request: web.Request) -> web.Response:
        """Analyze a completed prompt"""
        prompt_id = request.match_info["prompt_id"]
        prompt = self.system.queue.get(prompt_id)
        
        if not prompt:
            return web.json_response({"error": "Prompt not found"}, status=404)
        
        analysis = self.system.analyzer.analyze(prompt)
        
        return web.json_response({
            "quality": analysis.quality.value,
            "confidence": analysis.confidence,
            "needs_followup": analysis.needs_followup,
            "reason": analysis.reason,
            "suggested_followups": analysis.suggested_followups,
        })
    
    async def handle_control(self, request: web.Request) -> web.Response:
        """Handle control actions — sends commands to the real continuous_loop.py"""
        data = await request.json()
        action = data.get("action")

        command_map = {
            "start": LoopCommand.RESUME,
            "resume": LoopCommand.RESUME,
            "pause": LoopCommand.PAUSE,
            "run_once": LoopCommand.RUN_ONCE,
            "stop": LoopCommand.STOP,
            "approve": LoopCommand.APPROVE,
        }

        command = command_map.get(action)
        if not command:
            return web.json_response({"error": f"Unknown action: {action}"}, status=400)

        self.loop_controller.send_command(command)

        # Broadcast to WebSocket clients
        await self._broadcast({"type": "control", "action": action})

        # Return current loop status
        status = self.loop_controller.read_status()
        return web.json_response({"status": action, "loop": json.loads(status.to_json())})

    async def handle_loop_status(self, request: web.Request) -> web.Response:
        """Return real-time loop status from .loop.status"""
        status = self.loop_controller.read_status()
        return web.json_response(json.loads(status.to_json()))
    
    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self._clients.add(ws)
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    # Handle incoming messages if needed
        finally:
            self._clients.discard(ws)
        
        return ws
    
    async def _broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connected clients"""
        if not self._clients:
            return
        
        data = json.dumps(message)
        for ws in list(self._clients):
            try:
                await ws.send_str(data)
            except:
                self._clients.discard(ws)
    
    async def _run_loop(self) -> None:
        """Run the processing loop"""
        while self._running:
            result = await self.system.process_next()
            await self._broadcast({"type": "processed", "result": result})
            await asyncio.sleep(5)
    
    async def run(self) -> None:
        """Run the server"""
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()
        
        print(f"AIPM API Server running at http://localhost:{self.port}")
        print(f"Dashboard: http://localhost:{self.port}/control_center.html")
        
        # Keep running forever
        while True:
            await asyncio.sleep(3600)


async def main():
    """Main entry point"""
    server = APIServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
