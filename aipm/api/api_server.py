#!/usr/bin/env python3
"""
Ouroboros API Server

Provides REST API and WebSocket for the Control Center dashboard.

Endpoints:
- GET /api/prompts?limit=10 - Get next prompts
- GET /api/stats - Get statistics
- GET /api/completed?limit=10 - Get recent completed
- POST /api/prompts - Add new prompt
- GET /api/analyze/:id - Analyze a completed prompt
- WebSocket at /ws for real-time updates
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from aiohttp import web
    import aiohttp
except ImportError:
    print("Installing aiohttp...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"])
    from aiohttp import web
    import aiohttp

from ouroboros.core.ctrm_prompt_manager import CTRMPromptManager, CTRM_DB
from ouroboros.core.prompt_prioritizer import PromptPrioritizer
from ouroboros.core.response_analyzer import PromptResponseAnalyzer
from ouroboros.core.automated_loop import AutomatedPromptLoop


class OuroborosAPIServer:
    """REST API and WebSocket server for Control Center."""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.manager = CTRMPromptManager()
        self.prioritizer = PromptPrioritizer()
        self.analyzer = PromptResponseAnalyzer()
        self.loop = AutomatedPromptLoop()
        
        self.websockets = set()
        self.state = {
            'status': 'running',
            'loop_active': False,
            'processed_count': 0,
            'pending_count': 0,
            'uptime_start': datetime.now()
        }
    
    async def get_prompts(self, request: web.Request) -> web.Response:
        """GET /api/prompts?limit=10"""
        limit = int(request.query.get('limit', 10))
        
        scored = self.prioritizer.get_next_prompt(limit=limit)
        
        prompts = [
            {
                'id': p['id'],
                'prompt': p['prompt'],
                'priority': p['priority'],
                'confidence': p.get('ctrm_confidence', 0.5),
                'score': s
            }
            for p, s in scored
        ]
        
        return web.json_response(prompts)
    
    async def get_stats(self, request: web.Request) -> web.Response:
        """GET /api/stats"""
        queue_stats = self.manager.get_stats()
        
        # Get quality distribution
        analysis_summary = self.analyzer.get_summary()
        
        # Calculate uptime
        uptime = datetime.now() - self.state['uptime_start']
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        return web.json_response({
            'status': self.state['status'],
            'loop_active': self.state['loop_active'],
            'processed': queue_stats.get('completed_count', 0),
            'pending': queue_stats.get('pending_count', 0),
            'processing': queue_stats.get('processing_count', 0),
            'quality_distribution': analysis_summary.get('by_quality', {}),
            'uptime': f"{hours}h {minutes}m",
            'providers': self._get_provider_status()
        })
    
    async def get_completed(self, request: web.Request) -> web.Response:
        """GET /api/completed?limit=10"""
        limit = int(request.query.get('limit', 10))
        
        analyses = self.analyzer.analyze_all_completed(limit=limit)
        
        results = [
            {
                'id': a.prompt_id,
                'prompt': a.prompt[:100],
                'quality': a.quality.value,
                'confidence': a.confidence,
                'needs_followup': a.needs_followup,
                'followups': len(a.suggested_prompts),
                'timestamp': a.analysis_timestamp
            }
            for a in analyses
        ]
        
        return web.json_response(results)
    
    async def add_prompt(self, request: web.Request) -> web.Response:
        """POST /api/prompts"""
        data = await request.json()
        
        prompt_text = data.get('prompt', '')
        priority = data.get('priority', 5)
        source = data.get('source', 'api')
        
        if not prompt_text:
            return web.json_response({'error': 'Prompt required'}, status=400)
        
        prompt_id = self.manager.enqueue(
            prompt_text,
            priority=priority,
            source=source
        )
        
        # Broadcast update
        await self.broadcast_state()
        
        return web.json_response({
            'id': prompt_id,
            'status': 'enqueued'
        })
    
    async def analyze_prompt(self, request: web.Request) -> web.Response:
        """GET /api/analyze/:id"""
        prompt_id = request.match_info['id']
        
        analysis = self.analyzer.analyze_response(prompt_id)
        
        if not analysis:
            return web.json_response({'error': 'Not found'}, status=404)
        
        return web.json_response({
            'id': analysis.prompt_id,
            'prompt': analysis.prompt,
            'quality': analysis.quality.value,
            'confidence': analysis.confidence,
            'success_indicators': analysis.success_indicators,
            'failure_indicators': analysis.failure_indicators,
            'incomplete_indicators': analysis.incomplete_indicators,
            'actions_taken': analysis.actions_taken,
            'needs_followup': analysis.needs_followup,
            'followup_reason': analysis.followup_reason,
            'suggested_prompts': analysis.suggested_prompts
        })
    
    async def control_action(self, request: web.Request) -> web.Response:
        """POST /api/control"""
        data = await request.json()
        action = data.get('action', '')
        
        if action == 'start_loop':
            self.state['loop_active'] = True
            self.state['status'] = 'running'
            # Start the loop in background
            asyncio.create_task(self._run_loop_forever())
            
        elif action == 'pause_loop':
            self.state['loop_active'] = False
            self.state['status'] = 'paused'
            
        elif action == 'run_once':
            result = await self.loop.run_once()
            self.state['processed_count'] += 1
            
        elif action == 'clear_queue':
            # TODO: Implement
            pass
            
        elif action == 'emergency_stop':
            self.state['loop_active'] = False
            self.state['status'] = 'stopped'
        
        await self.broadcast_state()
        
        return web.json_response({'status': 'ok', 'action': action})
    
    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket /ws"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websockets.add(ws)
        
        # Send initial state
        await ws.send_json({
            'type': 'state_update',
            'state': self.state
        })
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    if data.get('type') == 'subscribe':
                        # Already subscribed
                        pass
                    
                    elif data.get('type') == 'gui_action':
                        # Handle GUI action
                        await self.control_action(web.Request(
                            app=request.app,
                            method='POST',
                            path='/api/control',
                            headers={'Content-Type': 'application/json'},
                            body=json.dumps({'action': data.get('action')}).encode()
                        ))
                    
                    elif data.get('type') == 'add_prompt':
                        # Add new prompt
                        await self.add_prompt(web.Request(
                            app=request.app,
                            method='POST',
                            path='/api/prompts',
                            headers={'Content-Type': 'application/json'},
                            body=json.dumps({
                                'prompt': data.get('prompt'),
                                'priority': data.get('priority', 5),
                                'source': data.get('source', 'websocket')
                            }).encode()
                        ))
        finally:
            self.websockets.discard(ws)
        
        return ws
    
    async def broadcast_state(self):
        """Broadcast state to all connected WebSockets."""
        if not self.websockets:
            return
        
        message = json.dumps({
            'type': 'state_update',
            'state': self.state
        })
        
        for ws in self.websockets:
            try:
                await ws.send_str(message)
            except:
                pass
    
    async def _run_loop_forever(self):
        """Run the automated loop in background."""
        while self.state['loop_active']:
            try:
                result = await self.loop.run_once()
                if result:
                    self.state['processed_count'] += 1
                await self.broadcast_state()
                await asyncio.sleep(60)  # 1 minute interval
            except Exception as e:
                print(f"Loop error: {e}")
                await asyncio.sleep(10)
    
    def _get_provider_status(self) -> Dict:
        """Get provider status (mock for now)."""
        return {
            'glm': {'available': True, 'used': 1920, 'limit': 2400},
            'gemini': {'available': False, 'used': 1500, 'limit': 1500},
            'claude': {'available': False, 'used': 10, 'limit': 25},
            'local': {'available': True, 'used': 45, 'limit': 1000}
        }
    
    def create_app(self) -> web.Application:
        """Create the aiohttp application."""
        app = web.Application()
        
        # REST API routes
        app.router.add_get('/api/prompts', self.get_prompts)
        app.router.add_get('/api/stats', self.get_stats)
        app.router.add_get('/api/completed', self.get_completed)
        app.router.add_post('/api/prompts', self.add_prompt)
        app.router.add_get('/api/analyze/{id}', self.analyze_prompt)
        app.router.add_post('/api/control', self.control_action)
        
        # WebSocket
        app.router.add_get('/ws', self.websocket_handler)
        
        # Static files
        # Look for .ouroboros in current working directory first (root)
        static_path = Path.cwd() / '.ouroboros'
        
        # Fallback to relative path from this file if not found
        if not static_path.exists():
            static_path = Path(__file__).resolve().parent.parent.parent.parent / '.ouroboros'
            
        if static_path.exists():
            print(f"Serving static files from: {static_path}")
            app.router.add_static('/', static_path, show_index=True)
        else:
            print(f"Warning: Static path not found: {static_path}")
        
        return app
    
    def run(self):
        """Run the server."""
        app = self.create_app()
        web.run_app(app, host='0.0.0.0', port=self.port)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Ouroboros API Server")
    parser.add_argument('--port', type=int, default=8080)
    
    args = parser.parse_args()
    
    print(f"\n🐍 Ouroboros API Server")
    print(f"="*50)
    print(f"API: http://localhost:{args.port}/api")
    print(f"WebSocket: ws://localhost:{args.port}/ws")
    print(f"Control Center: http://localhost:{args.port}/control_center.html")
    print(f"="*50 + "\n")
    
    server = OuroborosAPIServer(port=args.port)
    server.run()


if __name__ == "__main__":
    main()
