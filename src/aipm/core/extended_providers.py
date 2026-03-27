"""
Extended providers for AIPM

- ZAIProvider: Cloud LLM for high-dimensional reasoning
- PiAgentProvider: Local coding agent for execution
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from aipm.core.simple_bridge import PromptResult


@dataclass
class ZAIConfig:
    """Configuration for z.ai API"""
    api_key: str
    endpoint: str = "https://api.z.ai/v1/chat/completions"
    model: str = "glm-4-plus"  # or "glm-4-flash" for speed
    max_tokens: int = 8192
    timeout: float = 120.0


class ZAIProvider:
    """
    z.ai Cloud LLM Provider
    
    Used for:
    - Complex architectural decisions
    - Deep code refactoring
    - High-dimensional reasoning tasks
    - Failover when local models lack creative depth
    """
    
    def __init__(self, config: ZAIConfig):
        self.config = config
        self._client = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client
    
    async def process_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> PromptResult:
        """Process via z.ai Cloud API"""
        start_time = datetime.now()
        
        try:
            client = await self._get_client()
            
            response = await client.post(
                self.config.endpoint,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model or self.config.model,
                    "messages": messages,
                    "max_tokens": max_tokens or self.config.max_tokens,
                    "temperature": temperature,
                },
            )
            
            if response.status_code != 200:
                return PromptResult(
                    success=False,
                    content=None,
                    provider="z.ai",
                    error=f"HTTP {response.status_code}: {response.text}",
                )
            
            data = response.json()
            content = data["choices"][0]["message"].get("content", "")
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            
            return PromptResult(
                success=True,
                content=content,
                provider="z.ai",
                error=None,
                wait_time_ms=int(elapsed),
            )
        
        except Exception as e:
            return PromptResult(
                success=False,
                content=None,
                provider="z.ai",
                error=str(e),
            )
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


@dataclass
class PiAgentConfig:
    """Configuration for Pi Agent"""
    repo_path: Path
    coding_agent: str = "pi"  # Use 'pi' CLI directly
    default_model: str = "zai/glm-5"  # User's preferred model


class PiAgentProvider:
    """
    Pi Agent Provider - Executive Body
    
    Used for:
    - Complex implementation tasks
    - PR generation
    - Parallel experiment execution
    - Sandboxed code execution
    """
    
    def __init__(self, config: PiAgentConfig):
        self.config = config
        self.repo_path = Path(config.repo_path)
    
    async def execute_task(
        self,
        task: str,
        model: Optional[str] = None,
        sandbox: bool = True,
    ) -> PromptResult:
        """
        Execute a task via Pi Agent coding-agent
        
        This spawns a coding agent to implement the task
        and returns the results.
        """
        start_time = datetime.now()
        
        try:
            # Build the command - use 'pi' CLI directly
            cmd = [
                "pi",
                "--model", model or self.config.default_model,
            ]
            
            # Run the pi agent with task as input
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                input=task,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            
            if result.returncode == 0:
                return PromptResult(
                    success=True,
                    content=result.stdout,
                    provider="pi-agent",
                    error=None,
                    wait_time_ms=int(elapsed),
                )
            else:
                return PromptResult(
                    success=False,
                    content=result.stdout,
                    provider="pi-agent",
                    error=result.stderr,
                )
        
        except subprocess.TimeoutExpired:
            return PromptResult(
                success=False,
                content=None,
                provider="pi-agent",
                error="Task execution timed out (5 min)",
            )
        except Exception as e:
            return PromptResult(
                success=False,
                content=None,
                provider="pi-agent",
                error=str(e),
            )
    
    async def run_parallel_experiments(
        self,
        tasks: List[str],
        max_parallel: int = 3,
    ) -> List[PromptResult]:
        """
        Run multiple experiments in parallel using Pi Pods
        """
        results = []
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def run_one(task: str) -> PromptResult:
            async with semaphore:
                return await self.execute_task(task)
        
        # Run all tasks in parallel
        coroutines = [run_one(task) for task in tasks]
        results = await asyncio.gather(*coroutines)
        
        return list(results)


class HybridRouter:
    """
    Intelligent routing between providers
    
    Routes based on:
    - Task complexity
    - Required creativity depth
    - Speed requirements
    - Cost optimization
    """
    
    def __init__(
        self,
        local_provider,  # SimpleQueueBridge
        cloud_provider: Optional[ZAIProvider] = None,
        pi_provider: Optional[PiAgentProvider] = None,
    ):
        self.local = local_provider
        self.cloud = cloud_provider
        self.pi = pi_provider
    
    def score_complexity(self, prompt: str) -> float:
        """
        Score prompt complexity (0-1)
        
        Higher scores = more complex = route to cloud
        """
        complexity_indicators = [
            ("architect", 0.3),
            ("refactor", 0.25),
            ("redesign", 0.3),
            ("optimize", 0.2),
            ("implement", 0.15),
            ("complex", 0.2),
            ("multi-", 0.15),
            ("distributed", 0.25),
            ("integration", 0.2),
        ]
        
        score = 0.0
        prompt_lower = prompt.lower()
        
        for indicator, weight in complexity_indicators:
            if indicator in prompt_lower:
                score += weight
        
        return min(score, 1.0)
    
    def select_provider(self, prompt: str, prefer_speed: bool = False) -> str:
        """
        Select the best provider for a prompt
        
        Returns: "local", "cloud", or "pi"
        """
        complexity = self.score_complexity(prompt)
        
        # Speed preference overrides complexity
        if prefer_speed:
            return "local"
        
        # High complexity goes to cloud
        if complexity > 0.5 and self.cloud:
            return "cloud"
        
        # Implementation tasks go to Pi
        if "implement" in prompt.lower() and self.pi:
            return "pi"
        
        # Default to local
        return "local"
    
    async def process(
        self,
        prompt: str,
        messages: Optional[List[Dict]] = None,
        prefer_speed: bool = False,
    ) -> PromptResult:
        """Process prompt with best provider"""
        provider = self.select_provider(prompt, prefer_speed)
        
        if provider == "cloud" and self.cloud:
            return await self.cloud.process_chat(
                messages or [{"role": "user", "content": prompt}]
            )
        elif provider == "pi" and self.pi:
            return await self.pi.execute_task(prompt)
        else:
            # Use local
            return await self.local.process_chat(
                messages or [{"role": "user", "content": prompt}]
            )
