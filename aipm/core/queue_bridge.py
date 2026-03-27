"""
Python ↔ JavaScript Prompt Queue Bridge

Connects Python code to the Node.js prompt_queue.js for multi-provider
rate limit handling and automatic failover.
"""

import subprocess
import json
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ProviderStatus:
    """Status of a single provider."""
    name: str
    enabled: bool
    available: bool
    unavailable_reason: Optional[str]
    rate_limited: bool
    wait_time_ms: int
    used: int
    limit: int
    window_hours: float
    auth_type: str  # 'api_key', 'oauth', 'none'


@dataclass
class QueueStatus:
    """Full queue status."""
    pending: int
    completed: int
    failed: int
    processing: bool
    providers: Dict[str, ProviderStatus]


@dataclass
class PromptResult:
    """Result of a processed prompt."""
    success: bool
    content: Optional[str]
    provider: Optional[str]
    error: Optional[str]
    wait_time_ms: int


class PromptQueueBridge:
    """
    Bridge Python to the Node.js prompt queue manager.
    
    Usage:
        bridge = PromptQueueBridge()
        
        # Check status
        status = bridge.get_status()
        print(f"GLM available: {status.providers['glm'].available}")
        
        # Enqueue and process
        prompt_id = bridge.enqueue("Optimize the algorithm", priority=3)
        result = bridge.process_next()
        
        # Or use async for better integration
        result = await bridge.process_prompt("Generate hypothesis")
    """
    
    def __init__(self, 
                 queue_script: str = "./queue.sh",
                 project_root: Optional[Path] = None):
        self.queue_script = queue_script
        self.project_root = project_root or Path.cwd()
        self._status_cache: Optional[QueueStatus] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 5
    
    def _run_command(self, *args: str) -> subprocess.CompletedProcess:
        """Run queue.sh command."""
        cmd = [self.queue_script] + list(args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.project_root,
            timeout=60  # 1 minute timeout
        )
    
    def _parse_provider_status(self, data: Dict[str, Any]) -> ProviderStatus:
        """Parse provider status from JSON."""
        return ProviderStatus(
            name=data.get("name", "unknown"),
            enabled=data.get("enabled", False),
            available=data.get("available", False),
            unavailable_reason=data.get("unavailableReason"),
            rate_limited=data.get("rateLimited", False),
            wait_time_ms=data.get("waitTime", 0),
            used=data.get("used", 0),
            limit=data.get("limit", 0),
            window_hours=data.get("windowHours", 0),
            auth_type=data.get("auth", "api_key")
        )
    
    def get_status(self, use_cache: bool = True) -> QueueStatus:
        """
        Get current queue status.
        
        Args:
            use_cache: Use cached status if fresh (< 5s old)
        
        Returns:
            QueueStatus with pending/completed/failed counts and provider status
        """
        # Check cache
        if use_cache and self._status_cache and self._cache_time:
            age = (datetime.now() - self._cache_time).total_seconds()
            if age < self._cache_ttl_seconds:
                return self._status_cache
        
        result = self._run_command("status", "--json")
        
        if result.returncode != 0:
            raise RuntimeError(f"Queue status failed: {result.stderr}")
        
        data = json.loads(result.stdout)
        
        providers = {}
        for key, info in data.get("providers", {}).items():
            if info:
                providers[key] = self._parse_provider_status(info)
        
        status = QueueStatus(
            pending=data.get("pending", 0),
            completed=data.get("completed", 0),
            failed=data.get("failed", 0),
            processing=data.get("processing", False),
            providers=providers
        )
        
        # Update cache
        self._status_cache = status
        self._cache_time = datetime.now()
        
        return status
    
    def get_available_providers(self) -> List[str]:
        """Get list of currently available providers (sorted by priority)."""
        status = self.get_status()
        
        available = [
            name for name, provider in status.providers.items()
            if provider.enabled and provider.available and not provider.rate_limited
        ]
        
        # Priority order (from prompt_queue.js)
        priority_order = ["glm", "gemini", "claude", "local"]
        
        return sorted(available, key=lambda x: priority_order.index(x) if x in priority_order else 99)
    
    def get_wait_time(self) -> int:
        """Get milliseconds until next provider is available."""
        status = self.get_status()
        
        min_wait = 0
        for provider in status.providers.values():
            if provider.enabled and provider.rate_limited:
                if min_wait == 0 or provider.wait_time_ms < min_wait:
                    min_wait = provider.wait_time_ms
        
        return min_wait
    
    def enqueue(self, prompt: str, priority: int = 5, 
                max_attempts: int = 3, provider: Optional[str] = None) -> str:
        """
        Add a prompt to the queue.
        
        Args:
            prompt: The prompt text
            priority: Priority 1-10 (1 = highest)
            max_attempts: Maximum retry attempts
            provider: Preferred provider (optional)
        
        Returns:
            Prompt ID
        """
        # Build options JSON
        options = {
            "priority": priority,
            "maxAttempts": max_attempts
        }
        if provider:
            options["provider"] = provider
        
        result = self._run_command(
            "enqueue", 
            prompt,
            "--options", json.dumps(options)
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Enqueue failed: {result.stderr}")
        
        # Parse prompt ID from output like "📥 Enqueued: prompt_12345_abc (priority 5)"
        output = result.stdout.strip()
        if "Enqueued:" in output:
            return output.split("Enqueued:")[1].strip().split()[0]
        
        return f"prompt_{datetime.now().timestamp()}"
    
    def process_queue(self) -> List[PromptResult]:
        """
        Process all queued prompts.
        
        Returns:
            List of results for each processed prompt
        """
        result = self._run_command("process")
        
        if result.returncode != 0:
            return [PromptResult(
                success=False,
                content=None,
                provider=None,
                error=result.stderr,
                wait_time_ms=0
            )]
        
        # Parse results from output
        results = []
        output = result.stdout
        
        # Look for completion markers
        for line in output.split("\n"):
            if "✅ Completed:" in line:
                results.append(PromptResult(
                    success=True,
                    content=line,
                    provider=None,  # Would need to track
                    error=None,
                    wait_time_ms=0
                ))
            elif "❌ Failed:" in line:
                results.append(PromptResult(
                    success=False,
                    content=None,
                    provider=None,
                    error=line.split("Failed:")[-1].strip(),
                    wait_time_ms=0
                ))
        
        return results
    
    def clear(self, what: str = "all") -> None:
        """Clear queue items (all, completed, failed, pending)."""
        self._run_command("clear", what)
        self._status_cache = None  # Invalidate cache
    
    def retry_failed(self) -> int:
        """Retry all failed prompts. Returns count retried."""
        result = self._run_command("retry")
        # Parse count from output
        if "Retrying" in result.stdout:
            return int(result.stdout.split("Retrying")[1].split()[0])
        return 0
    
    def check_providers(self) -> Dict[str, bool]:
        """Check which providers are available (triggers OAuth checks)."""
        result = self._run_command("check")
        
        # Parse output for provider status
        providers = {}
        for line in result.stdout.split("\n"):
            if "🟢" in line:
                name = line.split("🟢")[1].strip().split()[0]
                providers[name] = True
            elif "🔴" in line or "🟡" in line:
                name = line.split("🔴")[1].strip().split()[0] if "🔴" in line else line.split("🟡")[1].strip().split()[0]
                providers[name] = False
        
        return providers
    
    def login(self, provider: str) -> bool:
        """Trigger OAuth login for a provider (gemini or claude)."""
        if provider not in ["gemini", "claude"]:
            raise ValueError(f"OAuth login only available for gemini/claude, not {provider}")
        
        result = self._run_command("login", provider)
        return result.returncode == 0
    
    def enable_provider(self, provider: str) -> None:
        """Enable a provider."""
        self._run_command("enable", provider)
        self._status_cache = None
    
    def disable_provider(self, provider: str) -> None:
        """Disable a provider."""
        self._run_command("disable", provider)
        self._status_cache = None
    
    # === Async Interface ===
    
    async def process_prompt_async(self, 
                                   prompt: str,
                                   priority: int = 5,
                                   preferred_provider: Optional[str] = None) -> PromptResult:
        """
        Async: Enqueue and process a single prompt.
        
        This is the primary method for Python code to send prompts
        through the multi-provider queue.
        """
        # Check if any provider available
        available = self.get_available_providers()
        
        if not available:
            wait_ms = self.get_wait_time()
            return PromptResult(
                success=False,
                content=None,
                provider=None,
                error="All providers rate limited",
                wait_time_ms=wait_ms
            )
        
        # Enqueue with priority
        prompt_id = self.enqueue(prompt, priority=priority, provider=preferred_provider)
        
        # Process in background
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self.process_queue)
        
        # Find our result
        for r in results:
            if r.success:
                return r
        
        # Return first failure if no success
        if results:
            return results[0]
        
        return PromptResult(
            success=False,
            content=None,
            provider=None,
            error="No results from queue processing",
            wait_time_ms=0
        )
    
    async def wait_for_availability(self, timeout_seconds: int = 300) -> List[str]:
        """
        Async: Wait until at least one provider is available.
        
        Args:
            timeout_seconds: Maximum time to wait
        
        Returns:
            List of available providers
        """
        start = datetime.now()
        
        while (datetime.now() - start).total_seconds() < timeout_seconds:
            available = self.get_available_providers()
            if available:
                return available
            
            wait_ms = self.get_wait_time()
            if wait_ms > 0:
                await asyncio.sleep(min(wait_ms / 1000, 30))
            else:
                await asyncio.sleep(5)
        
        return []


# === Convenience Functions ===

_bridge_instance: Optional[PromptQueueBridge] = None

def get_bridge(project_root: Optional[Path] = None) -> PromptQueueBridge:
    """Get or create singleton bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = PromptQueueBridge(project_root=project_root)
    return _bridge_instance


async def send_prompt(prompt: str, priority: int = 5) -> PromptResult:
    """Quick helper to send a prompt through the queue."""
    bridge = get_bridge()
    return await bridge.process_prompt_async(prompt, priority=priority)


# === CLI Interface ===

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Python Prompt Queue Bridge")
    parser.add_argument("command", choices=["status", "providers", "enqueue", "check"])
    parser.add_argument("--prompt", help="Prompt to enqueue")
    parser.add_argument("--priority", type=int, default=5, help="Priority 1-10")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    bridge = PromptQueueBridge()
    
    if args.command == "status":
        status = bridge.get_status()
        if args.json:
            data = {
                "pending": status.pending,
                "completed": status.completed,
                "failed": status.failed,
                "processing": status.processing,
                "providers": {
                    k: {
                        "available": v.available,
                        "rate_limited": v.rate_limited,
                        "used": v.used,
                        "limit": v.limit
                    }
                    for k, v in status.providers.items()
                }
            }
            print(json.dumps(data, indent=2))
        else:
            print(f"Pending: {status.pending}")
            print(f"Completed: {status.completed}")
            print(f"Failed: {status.failed}")
            print(f"Processing: {status.processing}")
            print("\nProviders:")
            for name, prov in status.providers.items():
                icon = "🟢" if prov.available and not prov.rate_limited else ("🟡" if prov.rate_limited else "🔴")
                print(f"  {icon} {name}: {prov.used}/{prov.limit} ({prov.window_hours}h)")
    
    elif args.command == "providers":
        available = bridge.get_available_providers()
        print(f"Available providers: {available}")
        if not available:
            wait = bridge.get_wait_time()
            print(f"Wait time: {wait/1000:.1f}s")
    
    elif args.command == "enqueue":
        if not args.prompt:
            print("Error: --prompt required")
            exit(1)
        prompt_id = bridge.enqueue(args.prompt, priority=args.priority)
        print(f"Enqueued: {prompt_id}")
    
    elif args.command == "check":
        providers = bridge.check_providers()
        for name, available in providers.items():
            icon = "🟢" if available else "🔴"
            print(f"{icon} {name}")
