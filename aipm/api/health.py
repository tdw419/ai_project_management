"""
Health Check endpoints for AIPM API Server.
Phase 1.2: Recovery Protocols.
"""

import asyncio
import time
import os
import psutil
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

from aiohttp import web

from aipm.config import CTRM_DB, QUEUE_DB, PROJECTS_DB
from aipm.sqlite_resilient import resilient_connection


class HealthCheck:
    """
    System health check monitoring.
    
    Checks:
    - Database connectivity (CTRM, Queue, Projects)
    - Disk space
    - Memory usage
    - Process status (continuous loop)
    - Model provider availability (LM Studio, Pi Agent)
    """
    
    def __init__(self, aipm_system=None):
        self.system = aipm_system
        self.start_time = datetime.now()
        
    async def get_full_health(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        db_health = await self.check_databases()
        system_health = self.check_system_resources()
        loop_health = await self.check_loop_status()
        provider_health = await self.check_providers()
        
        # Overall status
        all_ok = (
            all(db.get("status") == "ok" for db in db_health.values()) and
            system_health.get("disk", {}).get("status") == "ok" and
            provider_health.get("primary", {}).get("status") == "ok"
        )
        
        return {
            "status": "ok" if all_ok else "degraded",
            "timestamp": datetime.now().isoformat(),
            "uptime": str(datetime.now() - self.start_time),
            "databases": db_health,
            "system": system_health,
            "loop": loop_health,
            "providers": provider_health
        }
    
    async def check_databases(self) -> Dict[str, Any]:
        """Check all SQLite databases"""
        dbs = {
            "ctrm": CTRM_DB,
            "queue": QUEUE_DB,
            "projects": PROJECTS_DB
        }
        
        results = {}
        for name, path in dbs.items():
            status = "ok"
            error = None
            size_mb = 0
            
            if not path.exists():
                status = "missing"
                error = "Database file does not exist"
            else:
                try:
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                    with resilient_connection(path) as conn:
                        conn.execute("SELECT 1").fetchone()
                except Exception as e:
                    status = "error"
                    error = str(e)
            
            results[name] = {
                "status": status,
                "path": str(path),
                "size_mb": round(size_mb, 2),
                "error": error
            }
            
        return results
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check CPU, Memory, and Disk"""
        cpu_pct = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu": {"usage_pct": cpu_pct, "status": "ok" if cpu_pct < 90 else "high"},
            "memory": {
                "usage_pct": mem.percent,
                "available_gb": round(mem.available / (1024**3), 2),
                "status": "ok" if mem.percent < 90 else "high"
            },
            "disk": {
                "usage_pct": disk.percent,
                "free_gb": round(disk.free / (1024**3), 2),
                "status": "ok" if disk.percent < 95 else "critical"
            }
        }
    
    async def check_loop_status(self) -> Dict[str, Any]:
        """Check if continuous loop is running"""
        pid_file = Path(".loop.pid")
        if not pid_file.exists():
            return {"status": "stopped", "pid": None}
        
        try:
            pid = int(pid_file.read_text().strip())
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)
                if "python" in process.name().lower():
                    return {
                        "status": "running",
                        "pid": pid,
                        "cpu_pct": process.cpu_percent(),
                        "mem_mb": round(process.memory_info().rss / (1024 * 1024), 2),
                        "uptime": str(datetime.now() - datetime.fromtimestamp(process.create_time()))
                    }
            return {"status": "stale", "pid": pid, "error": "PID exists but process not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    async def check_providers(self) -> Dict[str, Any]:
        """Check model provider availability"""
        from aipm.core.simple_bridge import SimpleQueueBridge
        bridge = SimpleQueueBridge()
        
        lm_studio_ok = await bridge.is_available()
        
        # Check Pi Agent by trying to run 'pi --version' or similar
        pi_agent_ok = False
        try:
            import subprocess
            res = subprocess.run(["pi", "--version"], capture_output=True, timeout=2)
            pi_agent_ok = res.returncode == 0
        except:
            pass
            
        return {
            "primary": {
                "name": "LM Studio",
                "status": "ok" if lm_studio_ok else "unavailable",
                "url": bridge.lm_studio_url
            },
            "secondary": {
                "name": "Pi Agent",
                "status": "ok" if pi_agent_ok else "unavailable"
            }
        }


async def handle_health(request: web.Request) -> web.Response:
    """GET /api/health"""
    checker = HealthCheck()
    health = await checker.get_full_health()
    status_code = 200 if health["status"] == "ok" else 503
    return web.json_response(health, status=status_code)


async def handle_ping(request: web.Request) -> web.Response:
    """GET /ping"""
    return web.json_response({"status": "pong", "timestamp": datetime.now().isoformat()})
